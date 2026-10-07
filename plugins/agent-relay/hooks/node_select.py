"""Choose the node that starts the bridge outside a host (round2-fixes D50, round 2 findings R2-1 and R2-7).

The host entries pin an absolute node; a shell's or a background session's PATH may resolve an older one (nvm v12 in
round 2), which cannot run the bridge. Order: an explicit --node, the Claude user entry's command, the Codex table's
command, then PATH. The chosen node's version is checked before anything else happens.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable

MINIMUM_NODE = (22, 5, 0)
NODE_REASON = "the mailbox uses the built-in node:sqlite module, first shipped in Node 22.5.0"
CLAUDE_SERVER_NAME = "agent-relay"
CODEX_SERVER_NAME = "agent_relay"
_VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)\s*$")


class NodeSelectError(ValueError):
    """No usable node: ``reason`` is ``node-too-old`` or ``node-unavailable``; ``detail`` says which and why."""

    def __init__(self, reason: str, detail: str):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class SelectedNode:
    path: Path
    source: str  # --node, claude-entry, codex-entry or PATH
    version: str


def default_claude_json() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home()) / ".claude.json"


def default_codex_config() -> Path:
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    return (Path(codex_home) if codex_home else Path.home() / ".codex") / "config.toml"


def toml_table(text: str, header: str) -> dict[str, Any] | None:
    """Key/value lines of one table written by ``codex_fragment`` (values are JSON-compatible)."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
    except StopIteration:
        return None
    values: dict[str, Any] = {}
    for line in lines[start + 1:]:
        if line.strip().startswith("["):
            break
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        try:
            values[key.strip()] = json.loads(value.strip())
        except ValueError:
            values[key.strip()] = value.strip()
    return values


def _claude_entry(claude_json: Path) -> str | None:
    try:
        value = json.loads(claude_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    entry = (value.get("mcpServers") or {}).get(CLAUDE_SERVER_NAME) if isinstance(value, dict) else None
    command = entry.get("command") if isinstance(entry, dict) else None
    return command if isinstance(command, str) else None


def _codex_entry(codex_config: Path) -> str | None:
    try:
        table = toml_table(codex_config.read_text(encoding="utf-8"), f"[mcp_servers.{CODEX_SERVER_NAME}]")
    except (OSError, UnicodeError):
        return None
    command = (table or {}).get("command")
    return command if isinstance(command, str) else None


def node_version(path: Path) -> str | None:
    try:
        done = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def select_node(explicit: str | Path | None = None, *, claude_json: Path | None = None,
                codex_config: Path | None = None, which: Callable[[str], str | None] = shutil.which,
                version: Callable[[Path], str | None] = node_version) -> SelectedNode:
    """The first candidate that names an existing executable is used; it must be Node 22.5.0 or newer."""
    candidates: list[tuple[str, str | None]] = [
        ("--node", None if explicit is None else str(explicit)),
        ("claude-entry", _claude_entry(claude_json or default_claude_json())),
        ("codex-entry", _codex_entry(codex_config or default_codex_config())),
        ("PATH", which("node")),
    ]
    for source, command in candidates:
        if not command:
            continue
        path = Path(command) if os.sep in command else Path(which(command) or command)
        if not (path.is_file() and os.access(path, os.X_OK)):
            if source == "--node":
                raise NodeSelectError("node-unavailable", f"--node {command} is not an executable file")
            continue
        found = version(path)
        match = _VERSION.match(found or "")
        if match is None:
            raise NodeSelectError("node-unavailable", f"{path} ({source}) did not report a Node version")
        if tuple(map(int, match.groups())) < MINIMUM_NODE:
            raise NodeSelectError(
                "node-too-old", f"{path} ({source}) is Node {found.strip()}; agent-relay needs Node 22.5.0 or "
                f"newer because {NODE_REASON}. Install a newer Node or pass --node <path>.")
        return SelectedNode(path, source, found.strip())
    raise NodeSelectError("node-unavailable", "no node found in the host entries or on PATH; pass --node <path>")
