#!/usr/bin/env python3
"""Print narrow, non-secret host fragments for the opt-in native mailbox.

Printing does not install or merge user configuration. The server offers only
the ten mailbox tools, so no deny rules are needed (orchestrator-removal D92);
uninstall-claude still removes the ones agent-relay 0.4.0 and earlier wrote.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import tempfile
from typing import Any, Sequence

from host_backup import HostBackupError, backup_host_files, backup_message
from host_config_removal import _differences, add_claude_server, remove_claude_server, remove_codex_table
from native_collaboration_runtime import (LEGACY_WORKER_TOOLS, MAILBOX_TOOLS, NativeRuntimeError, StateHomeError,
                                          _servers_running, default_root, live_claude_sessions, status)


CLAUDE_SERVER_NAME = "agent-relay"
CODEX_SERVER_NAME = "agent_relay"


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
    """Return the server entry as reviewable data."""
    executable, server, database, data_home = _paths(root, node)
    return {
        "mcpServers": {CLAUDE_SERVER_NAME: {
            "command": executable, "args": [server],
            "env": {"BRIDGE_DB_PATH": database, "XDG_DATA_HOME": data_home},
        }},
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


def mailbox_approvals(tools=MAILBOX_TOOLS) -> str:
    """codex-gated-wake D70: the mailbox tools only read and write the mailbox, so a woken turn under the approval gate
    reads and replies without a card; any execution still meets the read-only sandbox. Same table Codex writes for 始终允许."""
    return "\n".join(f'[mcp_servers.{CODEX_SERVER_NAME}.tools.{tool}]\napproval_mode = "approve"\n' for tool in tools)


def approve_mailbox_tools(root: Path, node: Path, target: Path) -> str:
    """Add the missing approval tables to an existing entry that matches this runtime; refuse on any difference."""
    target = Path(target)
    existing, mode = _existing_regular(target)
    problems, found = _differences(existing, codex_fragment(root, node), CODEX_SERVER_NAME)
    if not found:
        raise ValueError("native Codex MCP server is not installed; run install-codex")
    if problems:
        raise ValueError("native Codex MCP entry differs, nothing was changed: " + "; ".join(problems))
    tables = re.findall(r'^\s*\[mcp_servers\.(?:"' + CODEX_SERVER_NAME + '"|' + CODEX_SERVER_NAME
                        + r')\.tools\.(?:"([^"]+)"|([A-Za-z0-9_-]+))\]', existing, re.MULTILINE)
    present = {quoted or bare for quoted, bare in tables}
    missing = [tool for tool in MAILBOX_TOOLS if tool not in present]
    if not missing:
        return "All mailbox tools are already approved for Codex; nothing changed."
    _atomic_write(target, existing.rstrip() + "\n\n" + mailbox_approvals(missing), mode)
    return "%d mailbox tool approval(s) added for Codex; restart Codex to load them." % len(missing)


def install_codex_config(root: Path, node: Path, target: Path) -> None:
    """Explicitly append only the native table; preserve every existing byte before it."""
    fragment = codex_fragment(root, node) + "\n" + mailbox_approvals()
    target = Path(target)
    existing, mode = _existing_regular(target)
    table = re.compile(r'^\s*\[mcp_servers\.(?:"' + CODEX_SERVER_NAME + '"|'
                       + CODEX_SERVER_NAME + r')(?:\.|\])', re.MULTILINE)
    if table.search(existing):
        raise ValueError("native Codex MCP server already exists; refusing to overwrite it")
    content = existing.rstrip() + ("\n\n" if existing.strip() else "") + fragment
    _atomic_write(target, content, mode)


def install_claude_config(root: Path, node: Path, settings: Path, claude_bin: str) -> None:
    """Add the user-scoped native MCP entry; the settings file is left alone (orchestrator-removal D92)."""
    fragment = claude_config(root, node)
    name = CLAUDE_SERVER_NAME
    add_claude_server(claude_bin, ["add-json", name, json.dumps(fragment["mcpServers"][name]),
                                   "--scope", "user"], name)


def remove_claude_deny_rules(settings: Path) -> int:
    """Remove exactly the deny rules agent-relay 0.4.0 and earlier wrote (safe-uninstall D46, orchestrator-removal
    D92); return how many were removed.
    Everything else in the file is kept; nothing is written when there is nothing to remove.
    """
    settings = Path(settings)
    current, mode = _existing_regular(settings)
    if not current:
        return 0
    try:
        value = json.loads(current)
    except json.JSONDecodeError as error:
        raise ValueError("Claude settings must be valid JSON") from error
    permissions = value.get("permissions") if isinstance(value, dict) else None
    deny = permissions.get("deny") if isinstance(permissions, dict) else None
    if not isinstance(deny, list):
        return 0
    ours = set(legacy_deny_rules())
    kept = [rule for rule in deny if rule not in ours]
    if len(kept) == len(deny):
        return 0
    permissions["deny"] = kept
    _atomic_write(settings, json.dumps(value, ensure_ascii=False, indent=2) + "\n", mode)
    return len(deny) - len(kept)


def _open_claude_users(root: Path, sessions: Path) -> str:
    """Why the deny rules must stay (round2-fixes D52), or "" when no Claude session or bridge is running.

    Open sessions count even with every bridge stopped: the host re-filters a session's cached tool list against
    the new settings. The caller counts too; it is itself an open session when an agent runs this."""
    reasons = []
    count = len({value["pid"] for value in live_claude_sessions(sessions).values()})
    if count:
        reasons.append("%d Claude Code session(s) still open" % count)
    try:
        bridges = _servers_running(root)
    except NativeRuntimeError:
        reasons.append("running bridge servers cannot be checked")
    else:
        if bridges:
            reasons.append("%d agent-relay bridge server(s) still running" % bridges)
    return "; ".join(reasons)


def _uninstall_claude_command(args: argparse.Namespace) -> str:
    command = ["python3", "-B", str(Path(__file__).resolve()), "uninstall-claude", "--confirm-uninstall",
               "--root", str(args.root), "--claude-settings", str(args.claude_settings),
               "--claude-json", str(args.claude_json)]
    if args.claude_bin != "claude":
        command += ["--claude-bin", str(args.claude_bin)]
    return " ".join(shlex.quote(part) for part in command)


def legacy_deny_rules() -> list[str]:
    return [f"mcp__{CLAUDE_SERVER_NAME}__{tool}" for tool in LEGACY_WORKER_TOOLS]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=("codex", "claude", "install-codex", "install-claude",
                                         "uninstall-codex", "uninstall-claude"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--node", type=Path, help="default: the node the host entries pin, else PATH's (D58)")
    parser.add_argument("--codex-config", type=Path, default=Path.home() / ".codex" / "config.toml")
    parser.add_argument("--claude-settings", type=Path,
                        default=Path.home() / ".claude" / "settings.json")
    parser.add_argument("--claude-json", type=Path,
                        default=Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home()) / ".claude.json",
                        help="the file the Claude CLI writes user-scoped MCP servers to (backed up first)")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--claude-sessions", type=Path, default=Path.home() / ".claude" / "sessions",
                        help="uninstall-claude: where Claude Code records its open sessions")
    parser.add_argument("--approve-mailbox-tools", action="store_true",
                        help="install-codex on an existing entry: add only the missing mailbox-tool approvals (D70)")
    parser.add_argument("--confirm-uninstall", action="store_true",
                        help="allow an uninstall command to remove host configuration")
    args = parser.parse_args(argv)
    try:
        args.root = args.root or default_root()
    except StateHomeError as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    if args.host.startswith("uninstall-") and not args.confirm_uninstall:
        print("uninstall-confirmation-required: rerun with --confirm-uninstall")
        return 1
    # adapter-node D58 (round 2 R2-13): the node the host entries pin, checked before the backup and any write.
    # Removal never refuses on the node: the fragment only serves the comparison, which accepts another node path.
    if args.host != "uninstall-claude":
        from node_select import NodeSelectError, select_node

        try:
            args.node = select_node(args.node, claude_json=args.claude_json, codex_config=args.codex_config).path
        except NodeSelectError as error:
            if args.host != "uninstall-codex":
                parser.exit(2, f"{parser.prog}: error: {error.reason}: {error.detail}\n")
            found = shutil.which("node")
            args.node = Path(found) if found else args.node
    # safe-uninstall (assumption 3): every host write keeps a private copy of the files it touches first.
    touched = {"install-codex": [args.codex_config], "uninstall-codex": [args.codex_config],
               "install-claude": [args.claude_settings, args.claude_json],
               "uninstall-claude": [args.claude_json, args.claude_settings]}.get(args.host)
    if touched is not None:
        try:
            print(backup_message(backup_host_files(touched)))
        except HostBackupError as error:
            parser.error("nothing was changed: " + str(error))
    if args.host == "uninstall-claude":
        # 先移除服务再移除拒绝规则，服务存在期间规则始终在（safe-uninstall D46）。
        try:
            state = remove_claude_server(args.claude_bin, CLAUDE_SERVER_NAME)
            still_open = _open_claude_users(args.root, args.claude_sessions)
            removed = 0 if still_open else remove_claude_deny_rules(args.claude_settings)
        except ValueError as error:
            parser.error(str(error))
        if still_open:
            print("Native Claude MCP entry %s; deny rules kept: %s. An open session would offer the upstream worker "
                  "tools as soon as the rules go (round 2 R2-10), so close every Claude Code session first, then "
                  "run this in a terminal:\n  %s" % (state, still_open, _uninstall_claude_command(args)))
            return 0
        rules = "%d deny rules removed" % removed if removed else "no deny rules to remove"
        print("Native Claude MCP entry %s; %s; restart Claude to apply." % (state, rules))
        return 0
    if args.node is None:
        parser.error("Node executable is unavailable")
    try:
        if args.host == "codex":
            result = codex_fragment(args.root, args.node)
        elif args.host == "claude":
            result = json.dumps(claude_config(args.root, args.node), indent=2, sort_keys=True)
        elif args.host == "install-codex" and args.approve_mailbox_tools:
            result = approve_mailbox_tools(args.root, args.node, args.codex_config)
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
