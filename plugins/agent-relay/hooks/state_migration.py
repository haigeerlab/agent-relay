#!/usr/bin/env python3
"""Move Spec Guard-era collaboration data into agent-relay: detect, back up, copy, verify, report.

`detect` is read-only. `migrate --confirm` re-runs every check and writes only when there is no blocker. The old
directories under ~/.spec-guard are never modified or deleted; host entries and permission rules are reported,
not changed (spec/state-migration.md, decisions D12-D14).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_collaboration_runtime import status as runtime_status  # noqa: E402
from session_delegation import DATABASE_FILENAME, DelegationError, DelegationStore  # noqa: E402

# Migration source: the names Spec Guard used before the split (D1).
OLD_RUNTIME = Path(".spec-guard") / "native-collaboration"
OLD_DELEGATION = Path(".spec-guard") / "session-delegation" / DATABASE_FILENAME
OLD_CLAUDE_SERVER = "spec-guard-native-collaboration"
OLD_CODEX_TABLE = "spec_guard_native_collaboration"
NEW_CLAUDE_SERVER = "agent-relay"
NEW_CODEX_TABLE = "agent_relay"
NEW_PARENT = Path(".agent-relay")

TERMINAL_DELEGATION_STATES = frozenset(("completed", "cancelled"))
NON_FINAL_WAKE_STATES = ("pending", "sending", "accepted", "unknown")


@dataclass
class Report:
    home: Path
    old_mailbox: dict[str, int] | None = None
    old_delegation: dict[str, int] | None = None
    wake_jobs: dict[str, int] = field(default_factory=dict)
    open_delegations: list[dict] = field(default_factory=list)
    running_servers: int = 0
    target_runtime: str = "absent"
    target_mailbox: dict[str, int] | None = None
    target_delegation_present: bool = False
    hosts: dict[str, bool] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        data = {key: value for key, value in self.__dict__.items() if key != "home"}
        data["verdict"] = "ready" if not self.blockers else "blocked"
        return data


def _paths(home: Path) -> dict[str, Path]:
    parent = home / NEW_PARENT
    return {"old_runtime": home / OLD_RUNTIME, "old_delegation": home / OLD_DELEGATION,
            "parent": parent, "runtime": parent / "runtime", "delegation": parent / "delegation",
            "backups": parent / "backups"}


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _snapshot(database: Path, workdir: Path) -> Path:
    """Copy a SQLite file with its WAL and SHM by plain reads, so the source directory is never touched.

    Opening a WAL database, even read-only, can create or update its -wal/-shm files next to it; the old
    Spec Guard directories must stay byte-identical, so every read goes through this copy.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    copy = workdir / database.name
    for suffix in ("", "-wal", "-shm"):
        source = Path(str(database) + suffix)
        if source.is_file():
            shutil.copyfile(source, Path(str(copy) + suffix))
    return copy


def table_counts(path: Path) -> dict[str, int]:
    with _read_only(path) as connection:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}


def _running_servers(old_runtime: Path) -> int:
    done = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True, check=False)
    marker = str(old_runtime / "dist" / "server.js")
    return sum(marker in line for line in done.stdout.splitlines())


def _host_entries(home: Path) -> dict[str, bool]:
    entries = {}
    try:
        servers = json.loads((home / ".claude.json").read_text(encoding="utf-8")).get("mcpServers", {})
    except (OSError, ValueError):
        servers = {}
    entries["claude_old"] = OLD_CLAUDE_SERVER in servers
    entries["claude_new"] = NEW_CLAUDE_SERVER in servers
    try:
        config = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    except OSError:
        config = ""
    for key, table in (("codex_old", OLD_CODEX_TABLE), ("codex_new", NEW_CODEX_TABLE)):
        entries[key] = re.search(r'^\s*\[mcp_servers\.(?:"' + table + '"|' + table + r')\]', config, re.M) is not None
    return entries


def inspect(home: Path, acknowledged: tuple[str, ...] = (),
            process_count: Callable[[Path], int] = _running_servers) -> Report:
    paths = _paths(home)
    report = Report(home)
    with tempfile.TemporaryDirectory(prefix="agent-relay-detect-") as scratch:
        _inspect_old(paths, report, acknowledged, Path(scratch))
    if report.old_mailbox is None and report.old_delegation is None:
        report.blockers.append("no Spec Guard collaboration state found; nothing to migrate")
    report.running_servers = process_count(paths["old_runtime"])
    if report.running_servers:
        report.blockers.append(f"{report.running_servers} old bridge server process(es) are running; close or restart "
                               "the sessions that use the old mailbox first (D13)")
    target = runtime_status(paths["runtime"])
    report.target_runtime = target.get("state", "unknown")
    if report.target_runtime != "ready":
        report.blockers.append("agent-relay runtime is not ready; install it with collaboration-ops first (D14)")
    target_mailbox = paths["runtime"] / "mailbox" / "bridge.sqlite"
    if target_mailbox.is_file():
        report.target_mailbox = table_counts(target_mailbox)
        if report.target_mailbox.get("messages", 0) or report.target_mailbox.get("agents", 0):
            report.blockers.append("agent-relay mailbox already has messages or agents; it is never merged (D14)")
    report.target_delegation_present = (paths["delegation"] / DATABASE_FILENAME).exists()
    if report.target_delegation_present:
        report.blockers.append("agent-relay delegation database already exists; it is never merged (D14)")
    report.hosts = _host_entries(home)
    return report


def _inspect_old(paths: dict[str, Path], report: Report, acknowledged: tuple[str, ...], scratch: Path) -> None:
    source = paths["old_runtime"] / "mailbox" / "bridge.sqlite"
    if source.is_file():
        mailbox = _snapshot(source, scratch / "mailbox")
        report.old_mailbox = table_counts(mailbox)
        with _read_only(mailbox) as connection:
            report.wake_jobs = dict(connection.execute(
                "SELECT state, COUNT(*) FROM wake_jobs WHERE state IN (%s) GROUP BY state"
                % ",".join("?" * len(NON_FINAL_WAKE_STATES)), NON_FINAL_WAKE_STATES).fetchall())
    if paths["old_delegation"].is_file():
        delegation = _snapshot(paths["old_delegation"], scratch / "delegation")
        report.old_delegation = table_counts(delegation)
        with _read_only(delegation) as connection:
            rows = connection.execute(
                "SELECT delegation_id, state, host_ref IS NOT NULL OR host_session_ref IS NOT NULL FROM delegations"
            ).fetchall()
        for delegation_id, state, launched in rows:
            if state in TERMINAL_DELEGATION_STATES:
                continue
            item = {"id": delegation_id[:6], "state": state, "launched": bool(launched),
                    "acknowledged": any(delegation_id.startswith(prefix) for prefix in acknowledged)}
            report.open_delegations.append(item)
            if launched:
                report.blockers.append(f"delegation {item['id']} is {state} and was launched; finish or cancel "
                                       "it under Spec Guard first (D12)")
            elif not item["acknowledged"]:
                report.blockers.append(f"delegation {item['id']} is {state} and never launched; acknowledge it with "
                                       f"--acknowledge-stale {item['id']} if it is dead (D12)")


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def _sqlite_copy(source: Path, target: Path) -> None:
    with _read_only(source) as reader, sqlite3.connect(target) as writer:
        reader.backup(writer)
    target.chmod(0o600)


def _file_copy(source: Path, target: Path) -> None:
    shutil.copy2(source, target)
    target.chmod(0o600)


def migrate(home: Path, acknowledged: tuple[str, ...] = (),
            process_count: Callable[[Path], int] = _running_servers) -> tuple[Report, dict]:
    report = inspect(home, acknowledged, process_count)
    if report.blockers:
        return report, {"state": "blocked"}
    paths = _paths(home)
    backup = paths["backups"] / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if backup.exists():
        return report, {"state": "blocked", "diagnostic": f"backup {backup.name} already exists"}
    _private_dir(paths["parent"])
    _private_dir(backup)
    result = {"state": "migrated", "backup": str(backup), "mismatches": []}
    old_mailbox = paths["old_runtime"] / "mailbox"
    if report.old_mailbox is not None:
        # Snapshot once into the backup, then copy the snapshot into place, so both hold the same data.
        _private_dir(backup / "mailbox" / "backups")
        with tempfile.TemporaryDirectory(prefix="agent-relay-migrate-") as scratch:
            _sqlite_copy(_snapshot(old_mailbox / "bridge.sqlite", Path(scratch)), backup / "mailbox" / "bridge.sqlite")
        for daily in sorted((old_mailbox / "backups").glob("*")):
            if daily.is_file():
                _file_copy(daily, backup / "mailbox" / "backups" / daily.name)
        if (paths["old_runtime"] / "data").is_dir():
            shutil.copytree(paths["old_runtime"] / "data", backup / "data")
        target = paths["runtime"] / "mailbox" / "bridge.sqlite"
        for suffix in ("", "-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
        _sqlite_copy(backup / "mailbox" / "bridge.sqlite", target)
        for daily in sorted((backup / "mailbox" / "backups").glob("*")):
            _file_copy(daily, paths["runtime"] / "mailbox" / "backups" / daily.name)
        if (backup / "data").is_dir():
            shutil.copytree(backup / "data", paths["runtime"] / "data", dirs_exist_ok=True)
            (paths["runtime"] / "data").chmod(0o700)  # copytree copies the source mode; the runtime requires 0700
        expected, actual = table_counts(backup / "mailbox" / "bridge.sqlite"), table_counts(target)
        if expected != actual:
            result["mismatches"].append({"database": "mailbox", "expected": expected, "actual": actual})
        result["mailbox"] = actual
    if report.old_delegation is not None:
        with tempfile.TemporaryDirectory(prefix="agent-relay-migrate-") as scratch:
            _sqlite_copy(_snapshot(paths["old_delegation"], Path(scratch)), backup / DATABASE_FILENAME)
        _private_dir(paths["delegation"])
        target = paths["delegation"] / DATABASE_FILENAME
        _sqlite_copy(backup / DATABASE_FILENAME, target)
        expected, actual = table_counts(backup / DATABASE_FILENAME), table_counts(target)
        if expected != actual:
            result["mismatches"].append({"database": "delegation", "expected": expected, "actual": actual})
        result["delegation"] = actual
        try:
            DelegationStore(paths["delegation"])
        except DelegationError as error:
            result["mismatches"].append({"database": "delegation", "diagnostic": str(error)})
    after = runtime_status(paths["runtime"])
    if after.get("state") != "ready":
        result["mismatches"].append({"runtime": after})
    if result["mismatches"]:
        result["state"] = "verification-failed"
    return report, result


def host_next_steps(report: Report) -> list[str]:
    steps = []
    if not report.hosts.get("claude_new") or not report.hosts.get("codex_new"):
        steps.append("Attach the new host entries with the collaboration-ops skill (install-claude / install-codex).")
    if report.hosts.get("claude_old") or report.hosts.get("codex_old"):
        steps.append("After the new entries work, remove the old entries with Spec Guard's own uninstall "
                     "(it installed them and removes them by exact match).")
    steps.append("Rename project allow rules from mcp__spec-guard-native-collaboration__bridge_* to "
                 "mcp__agent-relay__bridge_* by hand; agent-relay never edits permission files.")
    steps.append("~/.spec-guard/native-collaboration and ~/.spec-guard/session-delegation were not changed; remove "
                 "them yourself once you are satisfied (the backup above holds their data).")
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("detect", "migrate"))
    parser.add_argument("--confirm", action="store_true", help="required for migrate")
    parser.add_argument("--acknowledge-stale", action="append", default=[], metavar="ID_PREFIX",
                        help="a never-launched, non-terminal delegation the user confirms is dead (D12)")
    parser.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if any(not re.fullmatch(r"[0-9a-f-]{6,36}", prefix) for prefix in args.acknowledge_stale):
        parser.error("--acknowledge-stale takes a delegation id prefix of at least six hex characters")
    acknowledged = tuple(args.acknowledge_stale)
    if args.command == "detect":
        report = inspect(args.home, acknowledged)
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        return 0
    if not args.confirm:
        parser.error("migrate needs --confirm")
    report, result = migrate(args.home, acknowledged)
    output = {"report": report.as_dict(), "result": result}
    if result["state"] == "migrated":
        output["next_steps"] = host_next_steps(report)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if result["state"] == "migrated" else 1


if __name__ == "__main__":
    sys.exit(main())
