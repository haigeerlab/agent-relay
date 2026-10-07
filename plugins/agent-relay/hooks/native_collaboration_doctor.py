"""Report agent-relay's health on this Mac, read only (ops-commands D42).

Each check is ``{check, state, detail, next}`` with state ``ok``, ``warn`` or ``fail``. Nothing is written: host files
and the mailbox are only read, the probe runs on disposable data outside the runtime, and no session is started.
"""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from typing import Any, Callable, Iterable
from urllib.parse import quote

from native_collaboration_adapters import CLAUDE_SERVER_NAME, CODEX_SERVER_NAME
from state_migration import _snapshot
from native_collaboration_runtime import (DENIED_TOOLS, MAILBOX_BUSY_TIMEOUT, MAILBOX_SCHEMA_VERSIONS, MAILBOX_TOOLS,
                                          probe_runtime, status)

DEFAULT_MAX_PENDING = 100
OLD_BRIDGE = "/.spec-guard/native-collaboration/dist/server.js"


def _check(name: str, state: str, detail: str, next_step: str = "") -> dict[str, str]:
    return {"check": name, "state": state, "detail": detail, "next": next_step}


def codex_auto_approval(path: Path) -> tuple[bool, str]:
    """The bridge's rule (``codex-approval.ts``): guardian review or ``never`` at top level; unreadable fails closed."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, f"{path} does not exist (Codex defaults)"
    except (OSError, UnicodeError):
        return True, f"{path} could not be read, so auto-approval cannot be ruled out"
    for line in text.splitlines():
        if re.match(r"\s*\[", line):
            break
        key = re.match(r"\s*([A-Za-z_]+)\s*=", line)
        if not key or key.group(1) not in ("approvals_reviewer", "approval_policy"):
            continue
        value = re.match(r"""\s*[A-Za-z_]+\s*=\s*(?:"([^"]*)"|'([^']*)')\s*(?:#.*)?$""", line)
        if not value:
            return True, f"{path}: {key.group(1)} has a value that cannot be read, so auto-approval cannot be ruled out"
        found = value.group(1) if value.group(1) is not None else value.group(2)
        if key.group(1) == "approvals_reviewer" and found == "guardian_subagent":
            return True, f'{path} sets approvals_reviewer = "guardian_subagent" (AI auto-review)'
        if key.group(1) == "approval_policy" and found == "never":
            return True, f'{path} sets approval_policy = "never"'
    return False, f"{path} asks a person for approval"


def _runtime(root: Path) -> tuple[dict[str, str], bool]:
    current = status(root)
    if current["state"] != "ready":
        return _check("runtime", "fail", f"runtime at {root} is {current['state']}"
                      + (f": {current['diagnostic']}" if current.get("diagnostic") else ""),
                      "install it with native_collaboration_runtime.py install (after the user agrees)"), False
    if not current["bridge"]["current"]:
        return _check("runtime", "warn", "runtime is ready but its bridge is older than this plugin's",
                      "close the sessions using the mailbox, then run upgrade --confirm after the user agrees"), True
    return _check("runtime", "ok", "runtime ready; bridge matches this plugin"), True


def _probe(root: Path, probe: Callable[[Path], dict[str, Any]]) -> dict[str, str]:
    result = probe(root)
    if result.get("state") != "ready":
        return _check("probe", "fail", "the bridge did not start cleanly: " + str(result.get("diagnostic", result)),
                      "check Node and the runtime build; reinstall or upgrade after the user agrees")
    return _check("probe", "ok", f"the bridge starts and lists {result.get('toolCount')} tools")


def _mailbox(database: Path, original: Path | None = None) -> dict[str, str]:
    """Read `database` (a private copy of `original`)."""
    original = original or database
    if not original.exists():
        return _check("mailbox", "ok", "no mailbox yet; the bridge creates it on first use")
    try:
        with closing(sqlite3.connect("file:%s?mode=ro" % quote(str(database)), uri=True,
                                     timeout=MAILBOX_BUSY_TIMEOUT)) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in MAILBOX_SCHEMA_VERSIONS:
                return _check("mailbox", "fail", f"mailbox schema {version} is not one this plugin reads "
                              f"({', '.join(map(str, MAILBOX_SCHEMA_VERSIONS))})",
                              "update the agent-relay plugin or the runtime so they match")
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok":
                return _check("mailbox", "fail", f"quick_check: {integrity}",
                              "restore the newest backup under runtime/mailbox/backups after the user agrees")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
            backlog: list[tuple[str, int]] = []
            if "delivery_state" in columns:
                backlog = connection.execute(
                    """SELECT m.to_agent, COUNT(*) FROM messages m
                       WHERE m.to_agent != '*' AND COALESCE(m.delivery_state, 'queued') IN ('queued', 'sending', 'unknown')
                         AND NOT EXISTS (SELECT 1 FROM acknowledgements a WHERE a.message_id = m.id AND a.agent = m.to_agent)
                       GROUP BY m.to_agent ORDER BY 2 DESC""").fetchall()
    except sqlite3.Error as error:
        return _check("mailbox", "fail", f"cannot read the mailbox: {error}", "run status, then check the file")
    cap = DEFAULT_MAX_PENDING
    try:
        cap = int(os.environ.get("BRIDGE_MAX_PENDING_PER_RECIPIENT", cap))
    except ValueError:
        pass
    size = original.stat().st_size
    full = [(agent, count) for agent, count in backlog if count >= cap * 0.8]
    if full:
        return _check("mailbox", "warn", "undelivered backlog near the cap of %d: %s" % (
            cap, ", ".join(f"{agent}: {count}" for agent, count in full)),
            "ask those recipients to read their inbox, or retire identities nobody uses")
    measured = (f"largest backlog {backlog[0][0]}: {backlog[0][1]}" if backlog else "no undelivered backlog") \
        if "delivery_state" in columns else "backlog not measured (schema 2 has no delivery state)"
    return _check("mailbox", "ok", f"schema {version}, quick_check ok, {size} bytes, {measured}")


def _toml_table(text: str, header: str) -> dict[str, Any] | None:
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


def _hosts(root: Path, codex_config: Path, claude_json: Path, claude_settings: Path) -> dict[str, str]:
    server = str(root / "dist" / "server.js")
    database = str(root / "mailbox" / "bridge.sqlite")
    problems: list[str] = []
    attached: list[str] = []
    try:
        codex_text = codex_config.read_text(encoding="utf-8") if codex_config.exists() else ""
    except (OSError, UnicodeError):
        codex_text = None
        problems.append(f"{codex_config} cannot be read")
    if codex_text:
        table = _toml_table(codex_text, f"[mcp_servers.{CODEX_SERVER_NAME}]")
        env = _toml_table(codex_text, f"[mcp_servers.{CODEX_SERVER_NAME}.env]") or {}
        if table is not None:
            attached.append("Codex")
            if table.get("args") != [server] or env.get("BRIDGE_DB_PATH") != database:
                problems.append("the Codex entry points at another runtime")
            if table.get("enabled_tools") != list(MAILBOX_TOOLS):
                problems.append("the Codex entry does not enable exactly the ten mailbox tools")
    try:
        claude = json.loads(claude_json.read_text(encoding="utf-8")) if claude_json.exists() else {}
        settings = json.loads(claude_settings.read_text(encoding="utf-8")) if claude_settings.exists() else {}
    except (OSError, UnicodeError, ValueError):
        claude, settings = {}, {}
        problems.append("the Claude settings cannot be read")
    entry = (claude.get("mcpServers") or {}).get(CLAUDE_SERVER_NAME) if isinstance(claude, dict) else None
    if isinstance(entry, dict):
        attached.append("Claude")
        if entry.get("args") != [server] or (entry.get("env") or {}).get("BRIDGE_DB_PATH") != database:
            problems.append("the Claude entry points at another runtime")
        deny = ((settings.get("permissions") or {}).get("deny") or []) if isinstance(settings, dict) else []
        missing = [tool for tool in DENIED_TOOLS if f"mcp__{CLAUDE_SERVER_NAME}__{tool}" not in deny]
        if missing:
            problems.append("Claude deny rules missing for " + ", ".join(missing))
    if problems:
        return _check("host-entries", "fail", "; ".join(problems),
                      "reinstall the host entry with native_collaboration_adapters.py after the user agrees")
    if not attached:
        return _check("host-entries", "warn", "agent-relay is not attached to Claude or Codex",
                      "attach it with native_collaboration_adapters.py install-claude / install-codex after the user agrees")
    return _check("host-entries", "ok", "attached to " + " and ".join(attached) + "; entries match this runtime")


def _codex_approval(codex_config: Path) -> dict[str, str]:
    auto, reason = codex_auto_approval(codex_config)
    if auto:
        return _check("codex-approval", "warn", f"Codex runs with auto-approval ({reason}): Codex wake binding is "
                      "refused and pings to bound Codex sessions are held",
                      "set the Codex approval selector to 请求批准; never edit the file for the user")
    return _check("codex-approval", "ok", reason)


def _sessions(directory: Path, alive: Callable[[int], bool]) -> dict[str, dict[str, Any]]:
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


def _wake_bindings(database: Path, sessions_dir: Path, alive: Callable[[int], bool]) -> dict[str, str]:
    if not database.exists():
        return _check("wake-bindings", "ok", "no mailbox yet")
    try:
        with closing(sqlite3.connect("file:%s?mode=ro" % quote(str(database)), uri=True,
                                     timeout=MAILBOX_BUSY_TIMEOUT)) as connection:
            rows = connection.execute(
                "SELECT w.agent, w.target FROM wake_targets w JOIN agents a ON a.name = w.agent "
                "WHERE a.retired_at IS NULL ORDER BY w.agent").fetchall()
    except sqlite3.Error as error:
        return _check("wake-bindings", "fail", f"cannot read wake bindings: {error}", "run status, then check the file")
    sessions = _sessions(sessions_dir, alive)
    notes: list[str] = []
    problems: list[str] = []
    for agent, raw in rows:
        try:
            target = json.loads(raw)
        except ValueError:
            problems.append(f"{agent}: unreadable binding")
            continue
        if target.get("app") == "codex":
            notes.append(f"{agent}: Codex thread, liveness unknown")
            continue
        session = sessions.get(target.get("sessionId"))
        if session is None:
            problems.append(f"{agent}: its Claude session is not running")
        elif session.get("status") == "waiting":
            problems.append(f"{agent}: its Claude session is live but waiting (blocked on a prompt or input); "
                            "pings will not be handled")
        else:
            notes.append(f"{agent}: Claude session {session.get('status', 'live')}")
    if problems:
        return _check("wake-bindings", "warn", "; ".join(problems + notes),
                      "answer the waiting session, or have its owner unbind (wake: null) or retire a closed one")
    return _check("wake-bindings", "ok", "; ".join(notes) or "no wake-bound identities")


def _old_bridges(processes: Iterable[str]) -> dict[str, str]:
    count = sum(1 for line in processes if OLD_BRIDGE in line)
    if count:
        return _check("old-bridges", "warn", f"{count} Spec Guard collaboration bridge process(es) still running",
                      "close the sessions that still use Spec Guard's built-in collaboration")
    return _check("old-bridges", "ok", "no Spec Guard collaboration bridge running")


def _ps() -> list[str]:
    try:
        return subprocess.run(["ps", "-axo", "command"], check=True, capture_output=True, text=True,
                              timeout=30).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return []


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _probe_outside(root: Path, node: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agent-relay-doctor-") as scratch:
        return probe_runtime(root, node=node, scratch=Path(scratch))


def doctor(root: Path, *, home: Path | None = None, node: str = "node", codex_config: Path | None = None,
           claude_json: Path | None = None, claude_settings: Path | None = None,
           claude_sessions: Path | None = None, probe: Callable[[Path], dict[str, Any]] | None = None,
           processes: Callable[[], Iterable[str]] = _ps, alive: Callable[[int], bool] = _alive) -> dict[str, Any]:
    home = Path(home) if home else Path.home()
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    codex_config = Path(codex_config) if codex_config else (Path(codex_home) if codex_home else home / ".codex") / "config.toml"
    claude_json = Path(claude_json) if claude_json else home / ".claude.json"
    claude_settings = Path(claude_settings) if claude_settings else home / ".claude" / "settings.json"
    claude_sessions = Path(claude_sessions) if claude_sessions else home / ".claude" / "sessions"
    root = Path(root)
    database = root / "mailbox" / "bridge.sqlite"
    runtime, ready = _runtime(root)
    checks = [runtime]
    # Opening a WAL mailbox, even read-only, touches its -shm next to it, so every read goes through a private copy
    # made by plain file reads (as state-migration does); the live mailbox and its -wal/-shm stay untouched.
    with tempfile.TemporaryDirectory(prefix="agent-relay-doctor-mailbox-") as scratch:
        copy = _snapshot(database, Path(scratch)) if database.exists() else database
        if ready:
            checks += [_probe(root, probe or (lambda r: _probe_outside(r, node))), _mailbox(copy, database)]
        checks += [_hosts(root, codex_config, claude_json, claude_settings), _codex_approval(codex_config)]
        if ready:
            checks.append(_wake_bindings(copy, claude_sessions, alive))
    checks.append(_old_bridges(processes()))
    states = {check["state"] for check in checks}
    overall = "fail" if "fail" in states else "warn" if "warn" in states else "ok"
    return {"state": overall, "root": str(root), "checks": checks}
