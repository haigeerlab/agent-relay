#!/usr/bin/env python3
"""Map the native collaboration mailbox to one delegation config."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Callable
from urllib.parse import quote

from native_collaboration_adapters import CLAUDE_SERVER_NAME, claude_config
from session_delegation_codex import CommunicationServer


class BackendUnavailable(ValueError):
    """The native mailbox cannot be used safely."""


@dataclass(frozen=True)
class MailboxResultRoute:
    backend: str
    recipient: str
    key: str

    @property
    def transport(self) -> str:
        return "spec-guard-bridge"


@dataclass(frozen=True)
class DelegationBackend:
    name: str
    codex_server: CommunicationServer
    claude_server_name: str
    claude_config: dict[str, Any]
    claude_registration_probe: Callable[
        [str, int | None, str, str], bool | None
    ] | None
    claude_tools: tuple[str, ...]
    result_route_resolver: Callable[
        [str, str, str], MailboxResultRoute | None
    ]
    result_probe: Callable[[MailboxResultRoute, str], bool | None]


def _mailbox_connection(database: Path) -> sqlite3.Connection:
    database = Path(database)
    metadata = database.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077):
        raise ValueError("mailbox-database-unsafe")
    uri = "file:%s?mode=ro" % quote(str(database.absolute()))
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _route(recipient: str, delegation_id: str) -> MailboxResultRoute:
    if (not isinstance(recipient, str) or not recipient.strip()
            or len(recipient) > 128
            or any(ord(character) < 32 or ord(character) == 127
                   for character in recipient)):
        raise ValueError("mailbox-recipient-invalid")
    return MailboxResultRoute(
        "native", recipient, "spec-guard-result:" + delegation_id)


def native_result_route(database: Path, origin_host: str, origin_session: str,
                        delegation_id: str) -> MailboxResultRoute | None:
    """Resolve one live native recipient by exact host session, without messages."""
    try:
        with closing(_mailbox_connection(database)) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
                return None
            rows = connection.execute(
                "SELECT a.name, w.target FROM agents a JOIN wake_targets w "
                "ON w.agent=a.name WHERE a.retired_at IS NULL"
            ).fetchall()
            matches = []
            for row in rows:
                target = json.loads(row["target"])
                if (isinstance(target, dict)
                        and target.get("app") == origin_host
                        and target.get("sessionId") == origin_session):
                    matches.append(row["name"])
            if len(matches) != 1:
                return None
            return _route(matches[0], delegation_id)
    except (OSError, sqlite3.Error, ValueError, TypeError, json.JSONDecodeError):
        return None


def native_result_probe(database: Path, route: MailboxResultRoute,
                        sender: str) -> bool | None:
    """Check exact native result metadata; never select the message body."""
    if route.backend != "native":
        return None
    try:
        with closing(_mailbox_connection(database)) as connection:
            rows = connection.execute(
                "SELECT id FROM messages WHERE from_agent=? AND to_agent=? "
                "AND thread_id=?",
                (sender, route.recipient, route.key),
            ).fetchall()
            return len(rows) >= 1
    except (OSError, sqlite3.Error, ValueError):
        return None


def native_registration_probe(database: Path) -> Callable[
    [str, int | None, str, str], bool | None
]:
    """Read only the exact native agent and, for safe review, its wake binding."""
    database = Path(database)

    def probe(name: str, _pid: int | None, session_ref: str,
              intent: str) -> bool | None:
        try:
            metadata = database.lstat()
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) & 0o077):
                return None
            uri = "file:%s?mode=ro" % quote(str(database.absolute()))
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
                    return None
                agent = connection.execute(
                    "SELECT name FROM agents WHERE name=? AND retired_at IS NULL",
                    (name,),
                ).fetchall()
                if len(agent) != 1:
                    return False
                if intent != "safe-review":
                    return True
                rows = connection.execute(
                    "SELECT target FROM wake_targets WHERE agent=?", (name,)
                ).fetchall()
                if len(rows) != 1:
                    return False
                target = json.loads(rows[0][0])
                return (isinstance(target, dict) and target.get("app") == "claude"
                        and target.get("sessionId") == session_ref)
        except (OSError, sqlite3.Error, ValueError, TypeError, json.JSONDecodeError):
            return None

    return probe


def _regular(path: Path, label: str, *, executable: bool = False) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
    except (OSError, RuntimeError, TypeError) as error:
        raise BackendUnavailable(label + "-unavailable") from error
    if not resolved.is_file() or (executable and not resolved.stat().st_mode & 0o100):
        raise BackendUnavailable(label + "-unavailable")
    return resolved


def resolve_backend(
    native_root: Path,
    *,
    node: Path,
) -> DelegationBackend:
    node = _regular(node, "node", executable=True)
    generated = claude_config(native_root, node)
    server = generated["mcpServers"][CLAUDE_SERVER_NAME]
    codex = CommunicationServer(node, (server["args"][0],), dict(server["env"]))
    database = Path(native_root) / "mailbox" / "bridge.sqlite"
    return DelegationBackend(
        "native", codex, CLAUDE_SERVER_NAME,
        {"mcpServers": {CLAUDE_SERVER_NAME: server}},
        native_registration_probe(database),
        codex.enabled_tools,
        lambda host, session, delegation: native_result_route(
            database, host, session, delegation),
        lambda route, sender: native_result_probe(database, route, sender),
    )
