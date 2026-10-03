#!/usr/bin/env python3
"""Map the selected collaboration mailbox to one non-secret delegation config."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import sqlite3
import stat
from typing import Any, Callable
from urllib.parse import quote

from collaboration_adapters import MCP_SERVER_NAME, claude_mcp_config, mcp_url
from collaboration_auth_header import read_private_token
from collaboration_backend import selected_backend
from collaboration_runtime import read_runtime_config
from native_collaboration_adapters import CLAUDE_SERVER_NAME, claude_config
from session_delegation_codex import (
    CommunicationServer,
    HttpCommunicationServer,
    XATS_COMMUNICATION_TOOLS,
)


class BackendUnavailable(ValueError):
    """The selected mailbox cannot be used safely; never fall back implicitly."""


@dataclass(frozen=True)
class DelegationBackend:
    name: str
    codex_server: CommunicationServer | HttpCommunicationServer
    claude_server_name: str
    claude_config: dict[str, Any]
    claude_registration_probe: Callable[
        [str, int | None, str, str], bool | None
    ] | None
    claude_tools: tuple[str, ...]


def xats_registration_probe(database: Path) -> Callable[
    [str, int | None, str, str], bool | None
]:
    """Prove one Claude registration without reading messages or advancing cursors."""
    database = Path(database)

    def probe(name: str, pid: int | None, _session_ref: str,
              intent: str) -> bool | None:
        try:
            metadata = database.lstat()
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) & 0o077):
                return None
            uri = "file:%s?mode=ro" % quote(str(database.absolute()))
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(agents)")
                }
                required = {"agent_id", "agent_type", "team", "name", "runtime_ui_pid"}
                if not required <= columns:
                    return None
                if intent == "safe-review":
                    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
                        return None
                    rows = connection.execute(
                        "SELECT agent_id FROM agents WHERE agent_type='claude-code' "
                        "AND team='spec-guard-local' AND name=? AND runtime_ui_pid=?",
                        (name, pid),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT agent_id FROM agents WHERE agent_type='claude-code' "
                        "AND team='spec-guard-local' AND name=?",
                        (name,),
                    ).fetchall()
                return len(rows) == 1
        except (OSError, sqlite3.Error, ValueError):
            return None

    return probe


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
    marker: Path,
    native_root: Path,
    xats_config_dir: Path,
    *,
    node: Path,
    npx: Path,
    python_executable: Path,
    header_helper: Path,
    stdio_helper: Path,
) -> DelegationBackend:
    selection = selected_backend(marker, native_root)
    name = selection.get("backend")
    if name not in ("xats", "native"):
        raise BackendUnavailable("backend-" + str(name))
    if name == "native":
        node = _regular(node, "node", executable=True)
        generated = claude_config(native_root, node)
        server = generated["mcpServers"][CLAUDE_SERVER_NAME]
        environment = dict(server["env"])
        codex = CommunicationServer(
            node,
            (server["args"][0],),
            environment,
        )
        return DelegationBackend(
            "native", codex, CLAUDE_SERVER_NAME,
            {"mcpServers": {CLAUDE_SERVER_NAME: server}},
            native_registration_probe(Path(native_root) / "mailbox" / "bridge.sqlite"),
            codex.enabled_tools,
        )

    runtime = read_runtime_config(xats_config_dir)
    read_private_token(runtime.token_file)
    npx = _regular(npx, "npx", executable=True)
    python_executable = _regular(python_executable, "python", executable=True)
    header_helper = _regular(header_helper, "header-helper")
    stdio_helper = _regular(stdio_helper, "stdio-helper")
    helper = shlex.join((
        str(python_executable), "-B", str(header_helper),
        "--config-dir", str(Path(xats_config_dir)),
    ))
    return DelegationBackend(
        "xats",
        HttpCommunicationServer(
            mcp_url(runtime), helper, XATS_COMMUNICATION_TOOLS),
        MCP_SERVER_NAME,
        claude_mcp_config(
            stdio_helper, xats_config_dir, str(python_executable), str(npx)),
        xats_registration_probe(Path(xats_config_dir) / "messages.sqlite"),
        XATS_COMMUNICATION_TOOLS,
    )
