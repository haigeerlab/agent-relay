#!/usr/bin/env python3
"""Operator-only retirement of one native mailbox identity, keeping its backlog.

Rollback requires every native identity to be retired with no unread mail. Agents cannot call
bridge_retire (it is denied), and its default closes the backlog, which would mark unread mail
as handled. This command retires one exact name through the pinned CLI with --keep-backlog,
and only when that identity has no unacknowledged direct or broadcast delivery (an expired one does not count).
"""
from __future__ import annotations
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
from typing import Any, Sequence

from native_collaboration_runtime import (MAILBOX_SCHEMA_VERSIONS, StateHomeError, default_root, open_mailbox_read_only,
                                          status)


class RetireError(ValueError):
    """The identity cannot be retired safely."""


def _open_read_only(database: Path) -> sqlite3.Connection:
    metadata = database.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600):
        raise ValueError("native mailbox must be an owner-owned 0600 regular file")
    return open_mailbox_read_only(database)


def identity_state(database: Path, name: str) -> dict[str, Any]:
    """Read one identity and its unacknowledged deliveries from a single snapshot."""
    try:
        with closing(_open_read_only(Path(database))) as connection:
            connection.execute("BEGIN")
            if connection.execute("PRAGMA user_version").fetchone()[0] not in MAILBOX_SCHEMA_VERSIONS:
                raise ValueError("unsupported native mailbox schema")
            row = connection.execute(
                "SELECT registered_at, retired_at FROM agents WHERE name=?", (name,)).fetchone()
            if row is None:
                return {"state": "absent"}
            # cleanup-gaps D59: the bridge's unread rule (UNREAD_FOR): an expired message never blocks.
            states = "delivery_state" in {column[1] for column in connection.execute("PRAGMA table_info(messages)")}
            blocking = connection.execute("""
                SELECT m.id, CASE WHEN m.to_agent='*' THEN 'broadcast' ELSE %s END FROM messages m
                 WHERE (m.to_agent=? OR (m.to_agent='*' AND m.from_agent!=?
                                         AND m.created_at>=?))
                   AND %s
                   AND NOT EXISTS (SELECT 1 FROM acknowledgements a
                                    WHERE a.message_id=m.id AND a.agent=?)
                 ORDER BY m.id
            """ % (("COALESCE(m.delivery_state, 'queued')", "COALESCE(m.delivery_state, '') != 'expired'")
                   if states else ("'queued'", "1")), (name, name, row[0], name)).fetchall()
    except (OSError, sqlite3.Error, ValueError) as error:
        raise RetireError("native mailbox is unavailable: " + type(error).__name__) from error
    found = {"state": "retired" if row[1] else "active", "unacknowledged": len(blocking)}
    if blocking:
        found["blocking"] = [(identifier, state) for identifier, state in blocking]
    return found


def _blocking_text(blocking: list[tuple[int, str]]) -> str:
    """Up to ten `id state` pairs, never bodies (D59)."""
    shown = ", ".join("%d %s" % pair for pair in blocking[:10])
    return shown + (" and %d more" % (len(blocking) - 10) if len(blocking) > 10 else "")


def retire_identity(root: Path, node: str, name: str, note: str | None = None) -> dict[str, Any]:
    root = Path(root)
    if status(root)["state"] != "ready":
        raise RetireError("native runtime is not ready")
    database = root / "mailbox" / "bridge.sqlite"
    before = identity_state(database, name)
    if before["state"] == "absent":
        raise RetireError("no native identity is named exactly " + json.dumps(name))
    if before["state"] == "retired":
        return {"state": "already-retired", "name": name}
    if before["unacknowledged"]:
        raise RetireError("%s still has %d unacknowledged message(s) (%s); read and acknowledge them "
                          "first" % (name, before["unacknowledged"], _blocking_text(before["blocking"])))
    command = [node, str(root / "dist" / "cli.js"), "retire", name, "--keep-backlog"]
    if note:
        command += ["--note", note]
    environment = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
                   "BRIDGE_DB_PATH": str(database), "XDG_DATA_HOME": str(root / "data")}
    try:
        result = subprocess.run(command, env=environment, capture_output=True, text=True,
                                timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RetireError("pinned retire command failed: " + type(error).__name__) from error
    if result.returncode != 0 or identity_state(database, name)["state"] != "retired":
        raise RetireError("pinned retire command did not retire " + name)
    return {"state": "retired", "name": name}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="exact native identity name")
    parser.add_argument("--note")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--node", help="default: the node the host entries pin, else PATH's (refused below 22.5.0)")
    parser.add_argument("--confirm-retire", action="store_true", required=True,
                        help="operator confirms this identity's session has ended")
    args = parser.parse_args(argv)
    try:
        args.root = args.root or default_root()
    except StateHomeError as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    from node_select import NodeSelectError, select_node

    try:
        node = str(select_node(args.node).path)  # acceptance-kit-round2 D57 (round 2 R2-12)
        result = retire_identity(args.root, node, args.name, args.note)
    except NodeSelectError as error:
        result = {"state": "refused", "diagnostic": f"{error.reason}: {error.detail}"}
    except RetireError as error:
        result = {"state": "refused", "diagnostic": str(error)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] in ("retired", "already-retired") else 1


if __name__ == "__main__":
    raise SystemExit(main())
