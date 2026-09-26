#!/usr/bin/env python3
"""Explicit, opt-in installer for the pinned local Claude/Codex mailbox runtime.

This does not run the upstream setup, configure either host, start a service, or
touch the existing XATS mailbox. The ordinary collaboration entry still uses
XATS until a separate, reviewed cutover.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Sequence


BRIDGE_REPOSITORY = "https://github.com/WebisityStudio/claude-codex-mcp-bridge.git"
BRIDGE_COMMIT = "8f12c880cfdba73812b6ab7bc0f373fc467e0343"
MIN_NODE_VERSION = (22, 5, 0)


class NativeRuntimeError(ValueError):
    """The opt-in bridge runtime is absent, unsafe, or could not be installed."""


def default_root() -> Path:
    return Path.home() / ".spec-guard" / "native-collaboration"


def _private_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise NativeRuntimeError("native runtime directory is absent") from error
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077):
        raise NativeRuntimeError("native runtime directory must be owner-only and not a symlink")


def _regular_file(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise NativeRuntimeError(f"{label} is absent") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise NativeRuntimeError(f"{label} must be an owner-owned regular file")


def _owned_directory(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise NativeRuntimeError(f"{label} is absent") from error
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise NativeRuntimeError(f"{label} must be an owner-owned directory, not a symlink")


def status(root: Path) -> dict[str, Any]:
    """Inspect the optional runtime without creating it or opening the mailbox."""
    root = Path(root)
    if not root.exists() and not root.is_symlink():
        return {"state": "absent"}
    try:
        _private_directory(root)
        manifest = root / "manifest.json"
        _regular_file(manifest, "native runtime manifest")
        value = json.loads(manifest.read_text(encoding="utf-8"))
        if value != {"commit": BRIDGE_COMMIT}:
            raise NativeRuntimeError("native runtime revision does not match the audited commit")
        _owned_directory(root / "dist", "native bridge build directory")
        _regular_file(root / "dist" / "server.js", "native bridge server")
        mailbox = root / "mailbox"
        _private_directory(mailbox)
        backups = mailbox / "backups"
        _private_directory(backups)
        for backup in backups.iterdir():
            if backup.name.startswith("bridge-") and backup.name.endswith(".sqlite"):
                _regular_file(backup, "native mailbox backup")
                if stat.S_IMODE(backup.stat().st_mode) != 0o600:
                    raise NativeRuntimeError("native mailbox backup mode must be 0600")
        _private_directory(root / "data")
        database = mailbox / "bridge.sqlite"
        if database.exists() or database.is_symlink():
            _regular_file(database, "native mailbox")
            if stat.S_IMODE(database.stat().st_mode) != 0o600:
                raise NativeRuntimeError("native mailbox mode must be 0600")
    except (NativeRuntimeError, OSError, UnicodeError, json.JSONDecodeError) as error:
        return {"state": "invalid", "diagnostic": str(error)}
    return {"state": "ready", "commit": BRIDGE_COMMIT,
            "server": str(root / "dist" / "server.js"),
            "database": str(root / "mailbox" / "bridge.sqlite")}


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, check=True, capture_output=True,
                                text=True, timeout=300)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise NativeRuntimeError(f"native bridge install failed at {command[0]}") from error
    return result.stdout.strip()


def install_runtime(root: Path, *, node: str = "node", npm: str = "npm") -> dict[str, Any]:
    """Install one immutable upstream checkout; never run its broad setup command."""
    root = Path(root)
    if not root.is_absolute():
        raise NativeRuntimeError("native runtime path must be absolute")
    if root.exists() or root.is_symlink():
        raise NativeRuntimeError("native runtime already exists; refusing to overwrite it")
    version = _run([node, "--version"])
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version)
    if not match or tuple(map(int, match.groups())) < MIN_NODE_VERSION:
        raise NativeRuntimeError("native bridge requires Node.js 22.5.0 or newer")
    if root == default_root() and not root.parent.exists():
        root.parent.mkdir(mode=0o700)
    _owned_directory(root.parent, "native runtime parent")
    with tempfile.TemporaryDirectory(prefix=".native-stage-", dir=root.parent) as temporary:
        stage = Path(temporary)
        _run(["git", "init", "-q"], cwd=stage)
        _run(["git", "fetch", "--depth", "1", BRIDGE_REPOSITORY, BRIDGE_COMMIT], cwd=stage)
        _run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=stage)
        if _run(["git", "rev-parse", "HEAD"], cwd=stage) != BRIDGE_COMMIT:
            raise NativeRuntimeError("fetched bridge revision does not match the audited commit")
        _run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=stage)
        _run([npm, "run", "build"], cwd=stage)
        _regular_file(stage / "dist" / "server.js", "native bridge server")
        (stage / "mailbox").mkdir(mode=0o700)
        (stage / "mailbox" / "backups").mkdir(mode=0o700)
        (stage / "data").mkdir(mode=0o700)
        manifest = stage / "manifest.json"
        manifest.write_text(json.dumps({"commit": BRIDGE_COMMIT}) + "\n", encoding="utf-8")
        manifest.chmod(0o600)
        if root.exists() or root.is_symlink():
            raise NativeRuntimeError("native runtime appeared during install; refusing to overwrite it")
        stage.rename(root)
    return status(root)


def probe_runtime(root: Path, *, node: str = "node") -> dict[str, Any]:
    """Start the pinned server against disposable private data, never the live mailbox."""
    if status(root)["state"] != "ready":
        return {"state": "invalid", "diagnostic": "native runtime is not ready; run status first"}
    requests = (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "spec-guard-probe", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    with tempfile.TemporaryDirectory(prefix="native-probe-", dir=root) as temporary:
        probe = Path(temporary)
        (probe / "mailbox").mkdir(mode=0o700)
        (probe / "data").mkdir(mode=0o700)
        environment = {
            "PATH": os.environ.get("PATH", ""), "HOME": str(probe),
            "BRIDGE_DB_PATH": str(probe / "mailbox" / "bridge.sqlite"),
            "XDG_DATA_HOME": str(probe / "data"), "BRIDGE_BACKUPS": "0",
        }
        try:
            result = subprocess.run(
                [node, str(Path(root) / "dist" / "server.js")],
                input="".join(json.dumps(request) + "\n" for request in requests),
                cwd=probe, env=environment, capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"state": "invalid", "diagnostic": f"native MCP startup failed: {type(error).__name__}"}
    if result.returncode != 0:
        return {"state": "invalid", "diagnostic": "native MCP exited unsuccessfully; verify Node and pinned build"}
    try:
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        listing = next(response["result"]["tools"] for response in responses if response.get("id") == 2)
        names = {tool["name"] for tool in listing}
    except (ValueError, KeyError, StopIteration, TypeError, AttributeError):
        return {"state": "invalid", "diagnostic": "native MCP did not return a valid tool catalog"}
    if not {"bridge_register", "bridge_send", "bridge_inbox", "bridge_ack"} <= names:
        return {"state": "invalid", "diagnostic": "native MCP mailbox tools are incomplete"}
    return {"state": "ready", "toolCount": len(names)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "install", "probe"))
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument("--node", default="node")
    parser.add_argument("--npm", default="npm")
    args = parser.parse_args(argv)
    try:
        result = (status(args.root) if args.command == "status" else
                  probe_runtime(args.root, node=args.node) if args.command == "probe" else
                  install_runtime(args.root, node=args.node, npm=args.npm))
    except NativeRuntimeError as error:
        result = {"state": "error", "diagnostic": str(error)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] in ("absent", "ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
