"""Report agent-relay's health on this Mac, read only (ops-commands D42).

Each check is ``{check, state, detail, next}`` with state ``ok``, ``warn`` or ``fail``. Nothing is written: host files
and the mailbox are only read, the probe runs on disposable data outside the runtime, and no session is started.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
import plistlib
import os
import platform as python_platform
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterable

from native_collaboration_adapters import CLAUDE_SERVER_NAME, CODEX_SERVER_NAME
from node_select import NodeSelectError, select_node, toml_table
from state_migration import _snapshot
from native_collaboration_runtime import (MAILBOX_SCHEMA_VERSIONS, MAILBOX_TOOLS, live_claude_sessions,
                                          open_mailbox_read_only, pid_alive, probe_runtime, status)

DEFAULT_MAX_PENDING = 100
OLD_BRIDGE = "/.spec-guard/native-collaboration/dist/server.js"


def _check(name: str, state: str, detail: str, next_step: str = "") -> dict[str, str]:
    return {"check": name, "state": state, "detail": detail, "next": next_step}


def codex_auto_approval(path: Path) -> tuple[bool, str]:
    """Is the user's own Codex default auto-approved (guardian review or ``never`` at top level; unreadable fails closed)?
    Since codex-gated-wake (D66) this is information only: woken peer turns carry their own approval gate."""
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
    if current["state"] == "uninstalled":
        return _check("runtime", "warn", f"runtime build removed; message history kept at {current['history']}",
                      "install it again to use agent-relay (the history is kept), or delete it yourself"), False
    if current["state"] != "ready":
        return _check("runtime", "fail", f"runtime at {root} is {current['state']}"
                      + (f": {current['diagnostic']}" if current.get("diagnostic") else ""),
                      "install it with native_collaboration_runtime.py install (after the user agrees)"), False
    if not current["bridge"]["current"]:
        return _check("runtime", "warn", "runtime is ready but its bridge is older than this plugin's",
                      "close the sessions using the mailbox, then run upgrade --confirm after the user agrees"), True
    return _check("runtime", "ok", "runtime ready; bridge matches this plugin"), True


def _probe(root: Path, probe: Callable[[Path], dict[str, Any]], used: str = "") -> dict[str, str]:
    result = probe(root)
    if result.get("state") != "ready":
        return _check("probe", "fail", "the bridge did not start cleanly" + used + ": "
                      + str(result.get("diagnostic", result)),
                      "check Node and the runtime build; reinstall or upgrade after the user agrees")
    return _check("probe", "ok", f"the bridge starts{used} and lists {result.get('toolCount')} tools")


def _probe_with_selected_node(root: Path, node: str | None, claude_json: Path, codex_config: Path,
                              selector: Callable[..., Any] = select_node) -> dict[str, str]:
    """Probe with the node the host entries pin, as the controller does (round2-fixes D50, round 2 R2-1)."""
    try:
        selected = selector(node, claude_json=claude_json, codex_config=codex_config)
    except NodeSelectError as error:
        return _check("probe", "fail", error.detail, "install Node 22.5.0 or newer, or pass --node <path>")
    return _probe(root, lambda r: _probe_outside(r, str(selected.path)),
                  f" with node {selected.path} ({selected.version}, from {selected.source})")


def _toolchain(node: str | None, claude_json: Path, codex_config: Path, selector: Callable[..., Any]) -> dict[str, str]:
    """ci-macos D81: the Python running doctor and the node it would use, so a log or a report needs no guessing."""
    python = f"python {sys.executable} ({python_platform.python_version()})"
    try:
        selected = selector(node, claude_json=claude_json, codex_config=codex_config)
    except NodeSelectError as error:
        return _check("toolchain", "warn", f"{python}; no usable node: {error.detail}",
                      "install Node 22.5.0 or newer, or pass --node <path>")
    return _check("toolchain", "ok", f"{python}; node {selected.path} ({selected.version}, from {selected.source})")


def _mailbox(database: Path, original: Path | None = None) -> dict[str, str]:
    """Read `database` (a private copy of `original`)."""
    original = original or database
    if not original.exists():
        return _check("mailbox", "ok", "no mailbox yet; the bridge creates it on first use")
    try:
        with closing(open_mailbox_read_only(database)) as connection:
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


def _hosts(root: Path, codex_config: Path, claude_json: Path) -> dict[str, str]:
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
        table = toml_table(codex_text, f"[mcp_servers.{CODEX_SERVER_NAME}]")
        env = toml_table(codex_text, f"[mcp_servers.{CODEX_SERVER_NAME}.env]") or {}
        if table is not None:
            attached.append("Codex")
            if table.get("args") != [server] or env.get("BRIDGE_DB_PATH") != database:
                problems.append("the Codex entry points at another runtime")
            if table.get("enabled_tools") != list(MAILBOX_TOOLS):
                problems.append("the Codex entry does not enable exactly the ten mailbox tools")
    try:
        claude = json.loads(claude_json.read_text(encoding="utf-8")) if claude_json.exists() else {}
    except (OSError, UnicodeError, ValueError):
        claude = {}
        problems.append("the Claude settings cannot be read")
    entry = (claude.get("mcpServers") or {}).get(CLAUDE_SERVER_NAME) if isinstance(claude, dict) else None
    if isinstance(entry, dict):
        attached.append("Claude")
        if entry.get("args") != [server] or (entry.get("env") or {}).get("BRIDGE_DB_PATH") != database:
            problems.append("the Claude entry points at another runtime")
    if problems:
        return _check("host-entries", "fail", "; ".join(problems),
                      "reinstall the host entry with native_collaboration_adapters.py after the user agrees")
    if not attached:
        return _check("host-entries", "warn", "agent-relay is not attached to Claude or Codex",
                      "attach it with native_collaboration_adapters.py install-claude / install-codex after the user agrees")
    return _check("host-entries", "ok", "attached to " + " and ".join(attached) + "; entries match this runtime")


# codex-gated-wake D66a: the ChatGPT app version the per-turn approval gate was probed on (bridge codex-gate.ts).
MIN_CODEX_APP_VERSION = (26, 930)
CHATGPT_PLIST = Path("/Applications/ChatGPT.app/Contents/Info.plist")


def chatgpt_app_version() -> str | None:
    if sys.platform != "darwin" or not CHATGPT_PLIST.exists():
        return None
    try:
        done = subprocess.run(["/usr/bin/plutil", "-extract", "CFBundleShortVersionString", "raw", "-o", "-",
                               str(CHATGPT_PLIST)], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def _version_ok(version: str | None) -> bool:
    if not version or not re.fullmatch(r"\d+(\.\d+)*", version):
        return False
    parts = [int(part) for part in version.split(".")]
    return tuple(parts[:2] + [0] * (2 - len(parts[:2]))) >= MIN_CODEX_APP_VERSION


def _codex_approval(codex_config: Path, mailbox: Path, app_version: Callable[[], str | None]) -> dict[str, str]:
    """codex-gated-wake D68: say accurately what governs which turn; warn only when gated wake cannot run."""
    off = mailbox / "codex-gate.off"
    if off.exists():
        return _check("codex-approval", "warn", "gated Codex wake is off for this mailbox: an earlier woken turn did "
                      "not show the approval gate, so Codex pings are held and the user is notified",
                      f"check that Codex thread, then delete {off} to turn gated wake back on")
    try:
        attached = re.search(r"^\s*\[mcp_servers\.agent_relay\]", codex_config.read_text(encoding="utf-8"), re.M)
    except (OSError, UnicodeError):
        attached = None
    version = app_version() if attached else None
    if attached and not _version_ok(version):
        return _check("codex-approval", "warn", f"ChatGPT app version {version or 'cannot be read'}: gated Codex wake "
                      "needs 26.930 or later, so Codex pings are held and the user is notified",
                      "update the ChatGPT app")
    _auto, reason = codex_auto_approval(codex_config)
    return _check("codex-approval", "ok", f"{reason}. That default covers the user's own turns; the App's approval "
                  "selector applies per turn and is not stored in config.toml. Woken peer turns run read-only and ask "
                  "the user before any action (mailbox tools excepted when pre-approved)")


def _wake_bindings(database: Path, sessions_dir: Path, alive: Callable[[int], bool]) -> dict[str, str]:
    if not database.exists():
        return _check("wake-bindings", "ok", "no mailbox yet")
    try:
        with closing(open_mailbox_read_only(database)) as connection:
            rows = connection.execute(
                "SELECT w.agent, w.target FROM wake_targets w JOIN agents a ON a.name = w.agent "
                "WHERE a.retired_at IS NULL ORDER BY w.agent").fetchall()
    except sqlite3.Error as error:
        return _check("wake-bindings", "fail", f"cannot read wake bindings: {error}", "run status, then check the file")
    sessions = live_claude_sessions(sessions_dir, alive)
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


SCRIPT_EDITOR = "com.apple.ScriptEditor2"
TERMINAL_NOTIFIER = "fr.julienxx.oss.terminal-notifier"  # 2.0.0 and 3.1.0 alike (measured 2026-10-08)
NOTIFIER_CANDIDATES = ("/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier")  # never PATH
NOTIFY_ALLOWED_FLAG = 0x2000000  # measured 2026-10-08, undocumented: set on every app here that shows notifications
TEST_NOTIFICATION_TEXT = "agent-relay test notification"
ALLOW_NOTIFIER = ("System Settings → Notifications → terminal-notifier → Allow Notifications, then "
                  "`native_collaboration_runtime.py doctor --test-notification` to see one")
NO_CHANNEL = ("Script Editor (used by osascript) cannot be allowed until it asks, and it never does from the bridge: "
              "install terminal-notifier (`brew install terminal-notifier`, your choice) to see banners, or rely on the "
              "waiting list (doctor codex-waiting, or ask any session what is waiting for Codex)")


def find_notifier(candidates: Iterable[str] = NOTIFIER_CANDIDATES) -> Path | None:
    """notify-channel D83, as the bridge does: a fixed path resolving to a regular executable owned by this user or
    root and not writable by group or others."""
    for candidate in candidates:
        try:
            real = Path(candidate).resolve(strict=True)
            info = real.stat()
        except (OSError, RuntimeError):
            continue
        if (stat.S_ISREG(info.st_mode) and info.st_mode & 0o111 and not info.st_mode & 0o022
                and info.st_uid in (0, os.getuid())):
            return real
    return None


def read_notification_prefs() -> bytes | None:
    """Notification Center's per-app settings, read only (`defaults export`, nothing written)."""
    try:
        return subprocess.run(["defaults", "export", "com.apple.ncprefs", "-"], check=True, capture_output=True,
                              timeout=10).stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _allowed(entry: dict[str, Any]) -> bool:
    return bool(entry.get("auth")) and bool(int(entry.get("flags") or 0) & NOTIFY_ALLOWED_FLAG)


def _notifications(mailbox: Path, prefs: Callable[[], bytes | None], platform: str,
                   candidates: Iterable[str] = NOTIFIER_CANDIDATES) -> dict[str, str]:
    """acceptance-030-gaps D78, notify-channel D87: can the channel the bridge would use show its notices? Best effort;
    the Notification Center plist is undocumented."""
    if (mailbox / "notify.off").exists() or os.environ.get("AGENT_RELAY_NOTIFY") == "off":
        return _check("notifications", "ok", "desktop notifications are off by choice (notify.off); "
                      "the waiting list (codex-waiting) still shows what waits for Codex")
    if platform != "darwin":
        return _check("notifications", "ok", "not macOS, no desktop notifications; use the waiting list")
    notifier = find_notifier(candidates)
    try:
        data = prefs()
        apps = plistlib.loads(data)["apps"] if data else None
        bundle = TERMINAL_NOTIFIER if notifier else SCRIPT_EDITOR
        entry = next((app for app in apps if app.get("bundle-id") == bundle), None) if apps is not None else None
    except (plistlib.InvalidFileException, ValueError, KeyError, TypeError, AttributeError):
        apps = None
    channel = f"terminal-notifier ({notifier})" if notifier else "Script Editor (osascript)"
    advice = ALLOW_NOTIFIER if notifier else NO_CHANNEL
    if apps is None:
        return _check("notifications", "warn", f"cannot read the notification settings, so whether {channel} shows "
                      "the bridge's notices is unknown", advice)
    if entry is None:
        return _check("notifications", "warn", f"{channel} has never registered for notifications on this Mac, so "
                      "the bridge's notices are not shown", advice)
    if not _allowed(entry):
        return _check("notifications", "warn", f"{channel} appears not allowed to notify, so the bridge's notices "
                      "are dropped silently", advice)
    return _check("notifications", "ok", f"{channel} appears allowed to notify (a Focus mode can still hide "
                  "banners; doctor cannot see Focus)")


def send_test_notification(run: Callable[..., Any] = subprocess.run,
                           candidates: Iterable[str] = NOTIFIER_CANDIDATES) -> dict[str, Any]:
    """Show one notification through the channel the bridge would use (only on explicit request)."""
    notifier = find_notifier(candidates)
    try:
        if notifier:
            run([str(notifier), "-title", "agent-relay", "-subtitle", "doctor --test-notification",
                 "-group", "agent-relay-test"], input=TEST_NOTIFICATION_TEXT, text=True, check=False,
                capture_output=True, timeout=10)
        else:
            run(["osascript", "-e", "on run argv", "-e",
                 'display notification (item 1 of argv) with title "agent-relay"', "-e", "end run",
                 TEST_NOTIFICATION_TEXT], check=False, capture_output=True, timeout=10)
        sent = True
    except (OSError, subprocess.TimeoutExpired):
        sent = False
    return {"sent": sent, "text": TEST_NOTIFICATION_TEXT,
            "channel": f"terminal-notifier {notifier}" if notifier else "osascript (Script Editor)",
            "ask": "Did a banner appear? If not, see the notifications check."}


CODEX_WAITING_WARN_SECONDS = 600  # the D67 busy threshold


def _codex_waiting(database: Path) -> dict[str, str]:
    """acceptance-030-gaps D77: messages waiting for a Codex host (count, senders, ids; never bodies)."""
    if not database.exists():
        return _check("codex-waiting", "ok", "no mailbox yet")
    try:
        with closing(open_mailbox_read_only(database)) as connection:
            agents = {row[1] for row in connection.execute("PRAGMA table_info(agents)")}
            messages = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
            if not {"host_app", "retired_at"} <= agents or not {"delivery_state", "from_agent", "created_at"} <= messages:
                return _check("codex-waiting", "ok", "no Codex host recorded in this mailbox schema")
            rows = connection.execute(
                """SELECT m.to_agent, m.from_agent, m.id, m.created_at FROM messages m
                   JOIN agents ag ON ag.name = m.to_agent
                   WHERE ag.host_app = 'codex' AND ag.retired_at IS NULL
                     AND COALESCE(m.delivery_state, 'queued') NOT IN ('failed', 'expired')
                     AND NOT EXISTS (SELECT 1 FROM acknowledgements a WHERE a.message_id = m.id AND a.agent = m.to_agent)
                   ORDER BY m.to_agent, m.id""").fetchall()
    except sqlite3.Error as error:
        return _check("codex-waiting", "fail", f"cannot read the mailbox: {error}", "run status, then check the file")
    if not rows:
        return _check("codex-waiting", "ok", "nothing is waiting for a Codex task")
    grouped: dict[str, list[tuple[str, int]]] = {}
    old = False
    now = datetime.now(timezone.utc)
    for agent, sender, message_id, created in rows:
        grouped.setdefault(agent, []).append((sender, message_id))
        try:
            when = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            old = old or (now - when).total_seconds() > CODEX_WAITING_WARN_SECONDS
        except ValueError:
            old = True
    parts = []
    for agent, items in grouped.items():
        # Names are free text (notify-channel live check): one line, as the desktop notice shows them.
        senders = list(dict.fromkeys(" ".join(re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]", " ", str(sender)).split())
                                     for sender, _ in items))
        ids = ", ".join(f"#{message_id}" for _, message_id in items[:20])
        parts.append(f"{agent}: {len(items)} waiting from {', '.join(senders)} ({ids})")
    detail = "; ".join(parts)
    if old:
        return _check("codex-waiting", "warn", detail + "; some have waited more than 10 minutes",
                      "open that Codex task (or start it) so it reads its inbox, or ask the sender")
    return _check("codex-waiting", "ok", detail)


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


def _probe_outside(root: Path, node: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agent-relay-doctor-") as scratch:
        return probe_runtime(root, node=node, scratch=Path(scratch))


def doctor(root: Path, *, home: Path | None = None, node: str | None = None, codex_config: Path | None = None,
           claude_json: Path | None = None, claude_sessions: Path | None = None,
           probe: Callable[[Path], dict[str, Any]] | None = None,
           processes: Callable[[], Iterable[str]] = _ps, alive: Callable[[int], bool] = pid_alive,
           codex_app_version: Callable[[], str | None] = chatgpt_app_version,
           notification_prefs: Callable[[], bytes | None] = read_notification_prefs,
           platform: str = sys.platform, node_selector: Callable[..., Any] = select_node,
           notifier_candidates: Iterable[str] = NOTIFIER_CANDIDATES) -> dict[str, Any]:
    home = Path(home) if home else Path.home()
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    codex_config = Path(codex_config) if codex_config else (Path(codex_home) if codex_home else home / ".codex") / "config.toml"
    claude_json = Path(claude_json) if claude_json else home / ".claude.json"
    claude_sessions = Path(claude_sessions) if claude_sessions else home / ".claude" / "sessions"
    root = Path(root)
    database = root / "mailbox" / "bridge.sqlite"
    runtime, ready = _runtime(root)
    checks = [runtime, _toolchain(node, claude_json, codex_config, node_selector)]
    # Opening a WAL mailbox, even read-only, touches its -shm next to it, so every read goes through a private copy
    # made by plain file reads (as state-migration does); the live mailbox and its -wal/-shm stay untouched.
    with tempfile.TemporaryDirectory(prefix="agent-relay-doctor-mailbox-") as scratch:
        copy = _snapshot(database, Path(scratch)) if database.exists() else database
        if ready:
            probed = (_probe(root, probe) if probe else
                      _probe_with_selected_node(root, node, claude_json, codex_config, node_selector))
            checks += [probed, _mailbox(copy, database)]
        checks += [_hosts(root, codex_config, claude_json), _codex_approval(codex_config, root / "mailbox", codex_app_version)]
        if ready:
            checks.append(_wake_bindings(copy, claude_sessions, alive))
            checks.append(_codex_waiting(copy))
    checks.append(_notifications(root / "mailbox", notification_prefs, platform, notifier_candidates))
    checks.append(_old_bridges(processes()))
    states = {check["state"] for check in checks}
    overall = "fail" if "fail" in states else "warn" if "warn" in states else "ok"
    return {"state": overall, "root": str(root), "checks": checks}
