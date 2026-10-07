#!/usr/bin/env python3
"""Explicit, opt-in installer for the pinned local Claude/Codex mailbox runtime.

This does not run the upstream setup, configure either host, start a service, or
touch retained history from the retired transport. Native is the only current
collaboration runtime.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Callable, Sequence


# Mailbox schemas the Python readers understand: 2 (upstream 8f12c88) and 3 (delivery-state-machine adds
# nullable delivery columns only). A newer, unknown schema is refused rather than guessed at.
MAILBOX_SCHEMA_VERSIONS = (2, 3, 4, 5)
# Seconds a mailbox reader waits for a bridge's write lock, the bridge's own busy_timeout (identity-check D40).
MAILBOX_BUSY_TIMEOUT = 5.0
# Upstream commit the vendored bridge descends from (plugins/agent-relay/bridge/UPSTREAM.md).
BRIDGE_COMMIT = "8f12c880cfdba73812b6ab7bc0f373fc467e0343"
# SHA-256 of UPSTREAM.sha256 for the unmodified 8f12c88 tree: what a legacy git-installed runtime holds (D26).
UPSTREAM_TREE = "0573d6fcebe9b9ee57e430cbcca600d45d4d0eeba8c613266c201dd7c1f345a8"
MIN_NODE_VERSION = (22, 5, 0)


class NativeRuntimeError(ValueError):
    """The opt-in bridge runtime is absent, unsafe, or could not be installed."""


# The bridge is vendored next to these hooks (module bridge-vendoring, D23); UPSTREAM.sha256 records every
# file, and an install refuses a copy that differs from it (D24).
BRIDGE_SOURCE = Path(__file__).resolve().parent.parent / "bridge"
BRIDGE_MANIFEST = "UPSTREAM.sha256"
_PROVENANCE_FILES = frozenset((BRIDGE_MANIFEST, "UPSTREAM.md"))
_BUILD_OUTPUTS = frozenset(("node_modules", "dist", "dist.next", "dist.old"))


def bridge_tree(directory: Path) -> str:
    """The version mark of a bridge copy: the SHA-256 of its UPSTREAM.sha256 (D26)."""
    import hashlib

    return hashlib.sha256((Path(directory) / BRIDGE_MANIFEST).read_bytes()).hexdigest()


def verify_bridge_copy(directory: Path) -> None:
    """Refuse a bridge copy with any changed, missing or extra file against UPSTREAM.sha256."""
    import hashlib

    directory = Path(directory)
    try:
        lines = (directory / BRIDGE_MANIFEST).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise NativeRuntimeError("bridge copy has no readable UPSTREAM.sha256") from error
    expected: dict[str, str] = {}
    for line in lines:
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest) or not name:
            raise NativeRuntimeError("bridge UPSTREAM.sha256 has a malformed line")
        expected[name] = digest
    actual: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if relative.parts[0] in _BUILD_OUTPUTS or relative.as_posix() in _PROVENANCE_FILES:
            continue
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise NativeRuntimeError("bridge copy has a symlink or special file: " + relative.as_posix())
        if path.is_file():
            actual[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        changed = sorted(name for name in set(actual) & set(expected) if actual[name] != expected[name])
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise NativeRuntimeError("bridge copy differs from UPSTREAM.sha256: changed %s, missing %s, extra %s"
                                 % (changed[:3], missing[:3], extra[:3]))


STATE_HOME_VARIABLE = "AGENT_RELAY_HOME"


class StateHomeError(ValueError):
    """AGENT_RELAY_HOME is set to something that cannot be the state root."""


def state_home() -> Path:
    """The one place that decides agent-relay's state root (test-isolation, D21).

    `AGENT_RELAY_HOME` when set to an absolute path, else `~/.agent-relay`; an empty value
    counts as unset, a relative one is refused rather than resolved against the cwd.
    """
    value = os.environ.get(STATE_HOME_VARIABLE, "")
    if not value:
        return Path.home() / ".agent-relay"
    path = Path(value)
    if not path.is_absolute():
        raise StateHomeError(
            f"{STATE_HOME_VARIABLE} must be an absolute path, got {value!r}")
    return path


def default_root() -> Path:
    return state_home() / "runtime"


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


KEPT_ON_UNINSTALL = ("mailbox", "data")


def _uninstalled(root: Path) -> bool:
    """A runtime whose build was removed by `uninstall`: only the kept history and data remain."""
    try:
        if root.is_symlink() or not root.is_dir():
            return False
        names = {entry.name for entry in root.iterdir()}
    except OSError:
        return False
    return "mailbox" in names and names <= set(KEPT_ON_UNINSTALL)


def status(root: Path) -> dict[str, Any]:
    """Inspect the optional runtime without creating it or opening the mailbox."""
    root = Path(root)
    if not root.exists() and not root.is_symlink():
        return {"state": "absent"}
    if _uninstalled(root):
        return {"state": "uninstalled", "history": str(root / "mailbox")}
    try:
        _private_directory(root)
        manifest = root / "manifest.json"
        _regular_file(manifest, "native runtime manifest")
        value = json.loads(manifest.read_text(encoding="utf-8"))
        if value == {"commit": BRIDGE_COMMIT}:
            # Installed by git from upstream before bridge-vendoring: the unmodified 8f12c88 tree.
            bridge = {"source": "upstream-git", "tree": None,
                      "current": bridge_tree(BRIDGE_SOURCE) == UPSTREAM_TREE}
        elif (isinstance(value, dict) and set(value) == {"commit", "source", "tree"}
                and value["commit"] == BRIDGE_COMMIT and value["source"] == "vendored"
                and isinstance(value["tree"], str) and re.fullmatch(r"[0-9a-f]{64}", value["tree"])):
            bridge = {"source": "vendored", "tree": value["tree"],
                      "current": value["tree"] == bridge_tree(BRIDGE_SOURCE)}
        else:
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
    return {"state": "ready", "commit": BRIDGE_COMMIT, "bridge": bridge,
            "server": str(root / "dist" / "server.js"),
            "database": str(root / "mailbox" / "bridge.sqlite")}


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(command, cwd=cwd, check=True, capture_output=True,
                                text=True, timeout=300, env=env)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise NativeRuntimeError(f"native bridge install failed at {command[0]}") from error
    return result.stdout.strip()


def install_runtime(root: Path, *, node: str = "node", npm: str = "npm",
                    source: Path = BRIDGE_SOURCE) -> dict[str, Any]:
    """Build the runtime from the verified vendored bridge; never run its broad setup command."""
    root = Path(root)
    if not root.is_absolute():
        raise NativeRuntimeError("native runtime path must be absolute")
    if _uninstalled(root):
        return _reinstall_around_history(root, node=node, npm=npm, source=source)
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
        # bridge-vendoring D24: copy the plugin's bridge and check the copy itself, so what is
        # built is exactly what UPSTREAM.sha256 records; no git and no upstream fetch.
        shutil.copytree(source, stage, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(*_BUILD_OUTPUTS))
        stage.chmod(0o700)  # copytree copied the plugin directory's mode onto the private stage
        verify_bridge_copy(stage)
        # npm starts through `#!/usr/bin/env node`: put the chosen node first so npm runs on it, not on
        # whatever PATH resolves first (acceptance-kit-round2 D57, round 2 R2-12).
        npm_env = None
        if os.sep in str(node):
            npm_env = dict(os.environ, PATH=str(Path(node).parent) + os.pathsep + os.environ.get("PATH", ""))
        _run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=stage, env=npm_env)
        _run([npm, "run", "build"], cwd=stage, env=npm_env)
        _regular_file(stage / "dist" / "server.js", "native bridge server")
        (stage / "mailbox").mkdir(mode=0o700)
        (stage / "mailbox" / "backups").mkdir(mode=0o700)
        (stage / "data").mkdir(mode=0o700)
        manifest = stage / "manifest.json"
        manifest.write_text(json.dumps({"commit": BRIDGE_COMMIT, "source": "vendored",
                                        "tree": bridge_tree(stage)}) + "\n", encoding="utf-8")
        manifest.chmod(0o600)
        if root.exists() or root.is_symlink():
            raise NativeRuntimeError("native runtime appeared during install; refusing to overwrite it")
        stage.rename(root)
    return status(root)


# 固定提交的完整工具面：邮箱工具暴露给宿主，其余一律拒绝。上游新增工具必须先审查再归入其中一类，
# 否则 probe 失败，避免新的 worker 工具静默暴露给 Claude。
MAILBOX_TOOLS = (
    "bridge_register", "bridge_send", "bridge_inbox", "bridge_ack",
    "bridge_outbox", "bridge_agents", "bridge_sessions", "bridge_wake_status",
    "bridge_thread", "bridge_wait",
)
DENIED_TOOLS = (
    "bridge_retire", "ask_codex", "review_with_codex", "bridge_orchestrate_codex",
    "bridge_continue_codex", "bridge_orchestration_wait", "bridge_orchestration_status",
)


def probe_runtime(root: Path, *, node: str = "node", scratch: Path | None = None) -> dict[str, Any]:
    """Start the pinned server against disposable private data, never the live mailbox.

    The disposable data lives under the runtime unless ``scratch`` names another directory (``doctor`` uses one, so
    it writes nothing inside the runtime)."""
    if status(root)["state"] != "ready":
        return {"state": "invalid", "diagnostic": "native runtime is not ready; run status first"}
    requests = (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "agent-relay-probe", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    with tempfile.TemporaryDirectory(prefix="native-probe-", dir=scratch or root) as temporary:
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
    if not set(MAILBOX_TOOLS) <= names:
        return {"state": "invalid", "diagnostic": "native MCP mailbox tools are incomplete"}
    unreviewed = sorted(names - set(MAILBOX_TOOLS) - set(DENIED_TOOLS))
    if unreviewed:
        return {"state": "invalid",
                "diagnostic": "native MCP exposes unreviewed tools: " + ", ".join(unreviewed)}
    return {"state": "ready", "toolCount": len(names)}


UPGRADE_ROLLBACK = (
    "To go back to the previous runtime, stop every session using the mailbox, move runtime/mailbox and "
    "runtime/data into the previous directory, and rename it back to runtime. Its bridge opens the upgraded "
    "(schema 5) mailbox in compatible mode, but an older agent-relay plugin's hooks read only schema 2 (to 4): roll "
    "the plugin back too, or restore the mailbox from the backup (messages sent since are lost).")


def _servers_running(root: Path) -> int:
    """Bridge server processes started from this runtime (the upgrade must not swap under them)."""
    try:
        listing = subprocess.run(["ps", "-axo", "command"], check=True, capture_output=True,
                                 text=True, timeout=30).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise NativeRuntimeError("cannot list processes to check for running bridge servers") from error
    server = str(Path(root) / "dist" / "server.js")
    return sum(1 for line in listing.splitlines() if server in line)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def live_claude_sessions(directory: Path, alive: Callable[[int], bool] | None = None) -> dict[str, dict[str, Any]]:
    """Claude Code sessions whose `<pid>.json` names a live process, keyed by session id (and bridge session id)."""
    alive = alive or pid_alive
    found: dict[str, dict[str, Any]] = {}
    try:
        entries = list(directory.glob("*.json"))
    except OSError:
        return found
    for path in entries:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            continue
        if (isinstance(value, dict) and isinstance(value.get("pid"), int) and isinstance(value.get("sessionId"), str)
                and path.name == f"{value['pid']}.json" and alive(value["pid"])):
            for key in ("sessionId", "bridgeSessionId"):
                if isinstance(value.get(key), str):
                    found[value[key]] = value
    return found


def open_mailbox_read_only(database: Path, *, timeout: float = MAILBOX_BUSY_TIMEOUT) -> "sqlite3.Connection":
    """Open a mailbox (live or a private copy) read-only, on every supported Python's SQLite."""
    import sqlite3
    from urllib.parse import quote

    uri = "file:%s?mode=ro" % quote(str(Path(database).absolute()))
    if not any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm")):
        # No connection has the file open, so every committed row is in the file itself. Read it immutable: SQLite 3.43
        # (macOS /usr/bin/python3 3.9) cannot open such a WAL-mode file with mode=ro alone, and newer versions would
        # create -wal/-shm beside it (round2-fixes D51). A bridge starting meanwhile writes to its new -wal, not here.
        uri += "&immutable=1"
    return sqlite3.connect(uri, uri=True, timeout=timeout)


def _mailbox_counts(database: Path) -> dict[str, int]:
    from contextlib import closing

    if not database.is_file():
        return {}
    with closing(open_mailbox_read_only(database)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in ("agents", "messages", "acknowledgements", "wake_jobs") if table in tables}


def upgrade_runtime(root: Path, *, node: str = "node", npm: str = "npm", source: Path = BRIDGE_SOURCE,
                    backups: Path | None = None, running=_servers_running) -> dict[str, Any]:
    """Replace an installed runtime with one built from the plugin's bridge, keeping mailbox and data (D26).

    Refuses while a bridge server of this runtime runs. Backs the mailbox up first, builds the new runtime
    beside the old one, moves mailbox/ and data/ across, swaps the directories and verifies the result;
    any failure before the swap changes nothing, a failed verification swaps back. The previous directory is
    kept for the user to remove.
    """
    import time

    root = Path(root)
    before = status(root)
    if before["state"] != "ready":
        raise NativeRuntimeError("only a ready runtime can be upgraded: " + str(before.get("diagnostic", before["state"])))
    if before["bridge"]["current"]:
        return {"state": "current", "bridge": before["bridge"]}
    if running(root):
        raise NativeRuntimeError("a bridge server of this runtime is running; close every session using the "
                                 "mailbox first")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backups = Path(backups) if backups is not None else root.parent / "backups"
    backup = backups / stamp
    stage = root.parent / f".runtime-upgrade-{stamp}"
    previous = root.parent / f"runtime.previous-{stamp}"
    if stage.exists() or previous.exists() or backup.exists():
        raise NativeRuntimeError("an upgrade with this timestamp already exists; retry in a second")
    counts = _mailbox_counts(root / "mailbox" / "bridge.sqlite")

    if not backups.exists():
        backups.mkdir(mode=0o700)
    backups.chmod(0o700)  # it may predate this command with a wider mode; it holds full mailbox copies
    backup.mkdir(mode=0o700)
    shutil.copytree(root / "mailbox", backup / "runtime-mailbox")
    try:
        install_runtime(stage, node=node, npm=npm, source=source)
        for name in ("mailbox", "data"):
            shutil.rmtree(stage / name)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    moved: list[str] = []
    try:
        for name in ("mailbox", "data"):
            (root / name).rename(stage / name)
            moved.append(name)
        root.rename(previous)
    except BaseException:
        for name in moved:
            (stage / name).rename(root / name)
        shutil.rmtree(stage, ignore_errors=True)
        raise
    stage.rename(root)

    after = status(root)
    after_counts = _mailbox_counts(root / "mailbox" / "bridge.sqlite")
    if after["state"] != "ready" or not after["bridge"]["current"] or after_counts != counts:
        failed = root.parent / f".runtime-upgrade-failed-{stamp}"
        root.rename(failed)
        for name in ("mailbox", "data"):
            (failed / name).rename(previous / name)
        previous.rename(root)
        raise NativeRuntimeError(f"upgrade verification failed and was rolled back (new build kept at {failed})")
    return {"state": "upgraded", "bridge": after["bridge"], "counts": counts,
            "previous": str(previous), "backup": str(backup), "rollback": UPGRADE_ROLLBACK}


def uninstall_runtime(root: Path, *, running=_servers_running) -> dict[str, Any]:
    """Remove the runtime build and keep `mailbox/` (history, backups) and `data/` (safe-uninstall D47)."""
    root = Path(root)
    current = status(root)
    if current["state"] in ("absent", "uninstalled"):
        return current
    if current["state"] != "ready":
        raise NativeRuntimeError("only a ready runtime can be uninstalled: " + str(current.get("diagnostic")))
    if running(root):
        raise NativeRuntimeError("a bridge server of this runtime is running; close every session using the "
                                 "mailbox first")
    for entry in root.iterdir():
        if entry.name in KEPT_ON_UNINSTALL:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return status(root)


def _reinstall_around_history(root: Path, *, node: str, npm: str, source: Path) -> dict[str, Any]:
    """Build a fresh runtime beside an uninstalled one and move the kept mailbox and data into it."""
    import time

    counts = _mailbox_counts(root / "mailbox" / "bridge.sqlite")
    stage = root.parent / f".runtime-reinstall-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    try:
        install_runtime(stage, node=node, npm=npm, source=source)
        for name in KEPT_ON_UNINSTALL:
            shutil.rmtree(stage / name)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    moved: list[str] = []
    try:
        for name in KEPT_ON_UNINSTALL:
            if (root / name).exists():
                (root / name).rename(stage / name)
                moved.append(name)
        for name in KEPT_ON_UNINSTALL:
            if not (stage / name).exists():
                (stage / name).mkdir(mode=0o700)
        root.rmdir()
    except BaseException:
        for name in moved:
            (stage / name).rename(root / name)
        shutil.rmtree(stage, ignore_errors=True)
        raise
    stage.rename(root)
    if _mailbox_counts(root / "mailbox" / "bridge.sqlite") != counts:
        raise NativeRuntimeError("reinstall finished but the mailbox row counts changed; check the runtime")
    return status(root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "install", "probe", "upgrade", "doctor", "uninstall"))
    parser.add_argument("--confirm", action="store_true", help="required for upgrade and uninstall")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--node", help="default: doctor uses the node the host entries pin (then PATH); "
                                       "the other commands use PATH's node")
    parser.add_argument("--npm", help="default: the npm beside the chosen node, else PATH's")
    for option in ("--codex-config", "--claude-json", "--claude-settings", "--claude-sessions"):
        parser.add_argument(option, type=Path, help="doctor: read this file or directory instead of the default")
    args = parser.parse_args(argv)
    try:
        args.root = args.root or default_root()
    except StateHomeError as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    if args.command == "upgrade" and not args.confirm:
        parser.exit(2, f"{parser.prog}: error: upgrade replaces the runtime; rerun with --confirm after the "
                       "user agrees and every session using the mailbox is closed\n")
    if args.command == "uninstall" and not args.confirm:
        parser.exit(2, f"{parser.prog}: error: uninstall removes the runtime build (history is kept); rerun with "
                       "--confirm after the user agrees and every session using the mailbox is closed\n")
    if args.command in ("install", "upgrade"):
        # The node the host entries pin, checked before anything is built (acceptance-kit-round2 D57).
        from node_select import NodeSelectError, select_node

        try:
            chosen = select_node(args.node).path
        except NodeSelectError as error:
            parser.exit(2, f"{parser.prog}: error: {error.reason}: {error.detail}\n")
        args.node = str(chosen)
        beside = chosen.parent / "npm"
        args.npm = args.npm or (str(beside) if beside.is_file() and os.access(beside, os.X_OK) else "npm")
    elif args.command != "doctor":
        args.node = args.node or "node"
    if args.command == "doctor":
        from native_collaboration_doctor import doctor
        report = doctor(args.root, node=args.node, codex_config=args.codex_config, claude_json=args.claude_json,
                        claude_settings=args.claude_settings, claude_sessions=args.claude_sessions)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1 if report["state"] == "fail" else 0
    try:
        result = (upgrade_runtime(args.root, node=args.node, npm=args.npm) if args.command == "upgrade" else
                  uninstall_runtime(args.root) if args.command == "uninstall" else
                  status(args.root) if args.command == "status" else
                  probe_runtime(args.root, node=args.node) if args.command == "probe" else
                  install_runtime(args.root, node=args.node, npm=args.npm))
    except NativeRuntimeError as error:
        result = {"state": "error", "diagnostic": str(error)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] in ("absent", "ready", "upgraded", "current", "uninstalled") else 1


if __name__ == "__main__":
    raise SystemExit(main())
