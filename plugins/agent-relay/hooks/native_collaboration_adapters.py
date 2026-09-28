#!/usr/bin/env python3
"""Print narrow, non-secret host fragments for the opt-in native mailbox.

Printing does not install or merge user configuration. The Claude deny rules
must be applied before its MCP server is enabled; a config fragment alone would
expose upstream worker tools.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Sequence

from host_config_removal import remove_claude_server, remove_codex_table
from native_collaboration_runtime import DENIED_TOOLS, MAILBOX_TOOLS, default_root, status


CLAUDE_SERVER_NAME = "spec-guard-native-collaboration"
CODEX_SERVER_NAME = "spec_guard_native_collaboration"


def _paths(root: Path, node: Path) -> tuple[str, str, str, str]:
    root = Path(root)
    if status(root)["state"] != "ready":
        raise ValueError("native collaboration runtime is not ready; install it explicitly first")
    node = Path(node)
    if not node.is_absolute() or not node.is_file() or not os.access(node, os.X_OK):
        raise ValueError("Node executable must be an absolute executable file")
    return (str(node.resolve()), str(root / "dist" / "server.js"),
            str(root / "mailbox" / "bridge.sqlite"), str(root / "data"))


def codex_fragment(root: Path, node: Path) -> str:
    """Return one exact server table with a communication-only tool allowlist."""
    executable, server, database, data_home = _paths(root, node)
    return "\n".join((
        f"[mcp_servers.{CODEX_SERVER_NAME}]",
        f"command = {json.dumps(executable)}",
        f"args = {json.dumps([server])}",
        f"enabled_tools = {json.dumps(list(MAILBOX_TOOLS))}",
        "tool_timeout_sec = 300",
        "",
        f"[mcp_servers.{CODEX_SERVER_NAME}.env]",
        f"BRIDGE_DB_PATH = {json.dumps(database)}",
        f"XDG_DATA_HOME = {json.dumps(data_home)}",
        "",
    ))


def claude_config(root: Path, node: Path) -> dict[str, Any]:
    """Return the server entry and exact deny rules as separate, reviewable data."""
    executable, server, database, data_home = _paths(root, node)
    return {
        "mcpServers": {CLAUDE_SERVER_NAME: {
            "command": executable, "args": [server],
            "env": {"BRIDGE_DB_PATH": database, "XDG_DATA_HOME": data_home},
        }},
        "denyRules": [f"mcp__{CLAUDE_SERVER_NAME}__{tool}" for tool in DENIED_TOOLS],
    }


def _existing_regular(path: Path) -> tuple[str, int]:
    if not path.exists() and not path.is_symlink():
        return "", 0o600
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise ValueError("host configuration must be an owner-owned regular file, not a symlink")
    return path.read_text(encoding="utf-8"), stat.S_IMODE(metadata.st_mode)


def _atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid():
        raise ValueError("host configuration parent must be an owner-owned directory, not a symlink")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="native-config-",
                                     suffix=".tmp", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def install_codex_config(root: Path, node: Path, target: Path) -> None:
    """Explicitly append only the native table; preserve every existing byte before it."""
    fragment = codex_fragment(root, node)
    target = Path(target)
    existing, mode = _existing_regular(target)
    table = re.compile(r'^\s*\[mcp_servers\.(?:"' + CODEX_SERVER_NAME + '"|'
                       + CODEX_SERVER_NAME + r')(?:\.|\])', re.MULTILINE)
    if table.search(existing):
        raise ValueError("native Codex MCP server already exists; refusing to overwrite it")
    content = existing.rstrip() + ("\n\n" if existing.strip() else "") + fragment
    _atomic_write(target, content, mode)


def install_claude_config(root: Path, node: Path, settings: Path, claude_bin: str) -> None:
    """Install exact deny rules before the user-scoped native MCP entry."""
    fragment = claude_config(root, node)
    name = CLAUDE_SERVER_NAME
    try:
        existing_server = subprocess.run([claude_bin, "mcp", "get", name], check=False,
                                         capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("unable to inspect Claude MCP configuration") from error
    if existing_server.returncode == 0:
        raise ValueError("native Claude MCP server already exists; refusing to overwrite it")
    if "No MCP server named" not in existing_server.stdout + existing_server.stderr:
        raise ValueError("unable to confirm native Claude MCP server is absent")

    settings = Path(settings)
    current, mode = _existing_regular(settings)
    try:
        value = json.loads(current) if current else {}
    except json.JSONDecodeError as error:
        raise ValueError("Claude settings must be valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("Claude settings must be a JSON object")
    permissions = value.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        raise ValueError("Claude permissions must be a JSON object")
    deny = permissions.setdefault("deny", [])
    if not isinstance(deny, list) or not all(isinstance(rule, str) for rule in deny):
        raise ValueError("Claude deny rules must be a string list")
    deny.extend(rule for rule in fragment["denyRules"] if rule not in deny)
    _atomic_write(settings, json.dumps(value, ensure_ascii=False, indent=2) + "\n", mode)

    command = [claude_bin, "mcp", "add-json", name,
               json.dumps(fragment["mcpServers"][name]), "--scope", "user"]
    try:
        added = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Claude deny rules are installed, but MCP registration failed") from error
    if added.returncode != 0:
        raise ValueError("Claude deny rules are installed, but MCP registration failed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=("codex", "claude", "install-codex", "install-claude",
                                         "uninstall-codex", "uninstall-claude"))
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument("--node", type=Path, default=shutil.which("node"))
    parser.add_argument("--codex-config", type=Path, default=Path.home() / ".codex" / "config.toml")
    parser.add_argument("--claude-settings", type=Path,
                        default=Path.home() / ".claude" / "settings.json")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--confirm-uninstall", action="store_true",
                        help="allow an uninstall command to remove host configuration")
    args = parser.parse_args(argv)
    if args.host.startswith("uninstall-") and not args.confirm_uninstall:
        print("uninstall-confirmation-required: rerun with --confirm-uninstall")
        return 1
    if args.host == "uninstall-claude":
        # Claude 的拒绝规则保留：它们只拒绝本服务的工具，服务移除后无害，重新安装时仍然生效。
        try:
            state = remove_claude_server(args.claude_bin, CLAUDE_SERVER_NAME)
        except ValueError as error:
            parser.error(str(error))
        print("Native Claude MCP entry %s; deny rules kept; restart Claude to apply." % state)
        return 0
    if args.node is None:
        parser.error("Node executable is unavailable")
    try:
        if args.host == "codex":
            result = codex_fragment(args.root, args.node)
        elif args.host == "claude":
            result = json.dumps(claude_config(args.root, args.node), indent=2, sort_keys=True)
        elif args.host == "install-codex":
            install_codex_config(args.root, args.node, args.codex_config)
            result = "Native Codex MCP configuration installed; restart Codex to load it."
        elif args.host == "uninstall-codex":
            state = remove_codex_table(args.codex_config, codex_fragment(args.root, args.node),
                                       CODEX_SERVER_NAME)
            result = "Native Codex MCP entry %s; restart Codex to apply." % state
        else:
            install_claude_config(args.root, args.node, args.claude_settings, args.claude_bin)
            result = "Native Claude MCP configuration installed; restart Claude to load it."
    except ValueError as error:
        parser.error(str(error))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
