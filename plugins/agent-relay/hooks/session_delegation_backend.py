#!/usr/bin/env python3
"""Map the selected collaboration mailbox to one non-secret delegation config."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Any

from collaboration_adapters import MCP_SERVER_NAME, claude_mcp_config, mcp_url
from collaboration_auth_header import read_private_token
from collaboration_backend import selected_backend
from collaboration_runtime import read_runtime_config
from native_collaboration_adapters import CLAUDE_SERVER_NAME, claude_config
from session_delegation_codex import CommunicationServer, HttpCommunicationServer


class BackendUnavailable(ValueError):
    """The selected mailbox cannot be used safely; never fall back implicitly."""


@dataclass(frozen=True)
class DelegationBackend:
    name: str
    codex_server: CommunicationServer | HttpCommunicationServer
    claude_server_name: str
    claude_config: dict[str, Any]


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
    node = _regular(node, "node", executable=True)
    if name == "native":
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
        HttpCommunicationServer(mcp_url(runtime), helper),
        MCP_SERVER_NAME,
        claude_mcp_config(
            stdio_helper, xats_config_dir, str(python_executable), str(npx)),
    )
