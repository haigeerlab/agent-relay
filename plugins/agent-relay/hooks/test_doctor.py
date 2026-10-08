"""doctor reports agent-relay's health on this Mac, read only (ops-commands D42)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import sqlite3
import tempfile
import time
import sys
import unittest

from native_collaboration_adapters import CLAUDE_SERVER_NAME, codex_fragment
from native_collaboration_doctor import TEST_NOTIFICATION_TEXT, codex_auto_approval, doctor, send_test_notification
from native_collaboration_runtime import BRIDGE_COMMIT, BRIDGE_SOURCE, DENIED_TOOLS, bridge_tree, main

NODE = Path(sys.executable)
SCRIPT_EDITOR = "com.apple.ScriptEditor2"
# Measured on this Mac 2026-10-08: apps that show notifications have an auth value and flag 0x2000000.
SCRIPT_EDITOR_ALLOWED = {"bundle-id": SCRIPT_EDITOR, "flags": 0x12802056, "auth": 7}
SCRIPT_EDITOR_NEVER_ALLOWED = {"bundle-id": SCRIPT_EDITOR, "flags": 0x200e}  # the real entry when E2 was found


def prefs(*apps):
    return plistlib.dumps({"apps": [{"bundle-id": "com.apple.mail", "flags": 0x1280000e, "auth": 1}, *apps]})


class DoctorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-doctor-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()
        self.root = self.home / ".agent-relay" / "runtime"
        self.make_runtime()
        self.codex_config = self.home / ".codex" / "config.toml"
        self.claude_json = self.home / ".claude.json"
        self.claude_settings = self.home / ".claude" / "settings.json"
        self.sessions = self.home / ".claude" / "sessions"
        self.sessions.mkdir(parents=True)
        self.codex_config.parent.mkdir()
        self.codex_config.write_text('approval_policy = "on-request"\n\n' + codex_fragment(self.root, NODE))
        server = str(self.root / "dist" / "server.js")
        self.claude_json.write_text(json.dumps({"mcpServers": {CLAUDE_SERVER_NAME: {
            "command": str(NODE), "args": [server],
            "env": {"BRIDGE_DB_PATH": str(self.root / "mailbox" / "bridge.sqlite"),
                    "XDG_DATA_HOME": str(self.root / "data")}}}}))
        self.claude_settings.write_text(json.dumps({"permissions": {"deny": [
            f"mcp__{CLAUDE_SERVER_NAME}__{tool}" for tool in DENIED_TOOLS]}}))
        self.session("claude-live", "idle")
        self.processes = ["/usr/bin/node " + server]
        self.alive = {4242}

    def make_runtime(self):
        for sub in ("mailbox/backups", "data", "dist"):
            (self.root / sub).mkdir(parents=True, mode=0o700)
        for directory in (self.root, self.root / "mailbox", self.root / "mailbox" / "backups", self.root / "data",
                          self.root.parent):
            directory.chmod(0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps(
            {"commit": BRIDGE_COMMIT, "source": "vendored", "tree": bridge_tree(BRIDGE_SOURCE)}))
        self.database = self.root / "mailbox" / "bridge.sqlite"
        with sqlite3.connect(self.database) as connection:
            connection.executescript("""
                PRAGMA user_version = 5;
                CREATE TABLE agents (name TEXT PRIMARY KEY, retired_at TEXT);
                CREATE TABLE wake_targets (agent TEXT PRIMARY KEY, target TEXT NOT NULL);
                CREATE TABLE messages (id INTEGER PRIMARY KEY, to_agent TEXT, delivery_state TEXT);
                CREATE TABLE acknowledgements (message_id INTEGER, agent TEXT);
                INSERT INTO agents VALUES ('reviewer', NULL), ('codex-one', NULL);
                INSERT INTO wake_targets VALUES ('reviewer', '{"app":"claude","sessionId":"claude-live"}'),
                                                ('codex-one', '{"app":"codex","sessionId":"thread-1"}');
            """)
        self.database.chmod(0o600)

    def session(self, session_id, status, pid=4242):
        (self.sessions / f"{pid}.json").write_text(json.dumps(
            {"pid": pid, "sessionId": session_id, "status": status, "name": "review", "cwd": "/work/p"}))

    def run_doctor(self, **overrides):
        options = dict(home=self.home, codex_config=self.codex_config, claude_json=self.claude_json,
                       claude_settings=self.claude_settings, claude_sessions=self.sessions,
                       probe=lambda _root: {"state": "ready", "toolCount": 17},
                       processes=lambda: self.processes, alive=lambda pid: pid in self.alive,
                       codex_app_version=lambda: "26.930.61225",
                       notification_prefs=lambda: prefs(SCRIPT_EDITOR_ALLOWED), platform="darwin")
        options.update(overrides)
        return doctor(self.root, **options)

    def states(self, report):
        return {check["check"]: check["state"] for check in report["checks"]}

    def find(self, report, name):
        return next(check for check in report["checks"] if check["check"] == name)

    def test_a_healthy_setup_is_ok_and_nothing_is_written(self):
        files = [self.codex_config, self.claude_json, self.claude_settings, self.database]
        before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in files}
        report = self.run_doctor()
        self.assertEqual(report["state"], "ok", json.dumps(report, indent=1))
        self.assertEqual(set(self.states(report).values()), {"ok"})
        self.assertEqual(self.find(report, "wake-bindings")["detail"].count("unknown"), 1, "Codex liveness")
        for check in report["checks"]:
            self.assertTrue(check["detail"], check)
        self.assertEqual({path: (path.stat().st_mtime_ns, path.read_bytes()) for path in files}, before)

    def test_a_live_wal_mailbox_and_its_wal_and_shm_files_are_not_touched(self):
        holder = sqlite3.connect(self.database, isolation_level=None)
        self.addCleanup(holder.close)
        holder.executescript("PRAGMA journal_mode = WAL; INSERT INTO messages (to_agent, delivery_state) VALUES ('reviewer', 'queued');")
        files = [Path(str(self.database) + suffix) for suffix in ("", "-wal", "-shm")]
        self.assertTrue(all(path.exists() for path in files))
        before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in files}
        time.sleep(0.05)
        report = self.run_doctor()
        self.assertEqual(self.find(report, "mailbox")["state"], "ok", report)
        self.assertIn("reviewer: 1", self.find(report, "mailbox")["detail"], "uncheckpointed WAL rows are seen")
        self.assertEqual({path: (path.stat().st_mtime_ns, path.read_bytes()) for path in files}, before)

    def test_an_old_chatgpt_app_or_a_turned_off_gate_warns(self):
        # codex-gated-wake D66/D68.
        self.codex_config.write_text(codex_fragment(self.root, NODE))
        for version in ("26.929.1", None):
            with self.subTest(version=version):
                check = self.find(self.run_doctor(codex_app_version=lambda: version), "codex-approval")
                self.assertEqual(check["state"], "warn")
                self.assertIn("26.930 or later", check["detail"])
                self.assertIn("update the ChatGPT app", check["next"])
        off = self.root / "mailbox" / "codex-gate.off"
        off.write_text("turn t of thread: missing\n")
        check = self.find(self.run_doctor(), "codex-approval")
        self.assertEqual(check["state"], "warn")
        self.assertIn("gated Codex wake is off", check["detail"])
        self.assertIn(str(off), check["next"])

    def test_no_codex_entry_means_no_version_warning(self):
        self.codex_config.write_text("")
        check = self.find(self.run_doctor(codex_app_version=lambda: None), "codex-approval")
        self.assertEqual(check["state"], "ok", check)

    def test_warnings_name_the_problem_and_the_next_step(self):
        self.codex_config.write_text('approvals_reviewer = "guardian_subagent"\n\n' + codex_fragment(self.root, NODE))
        self.session("claude-live", "waiting")
        self.processes.append("node /Users/x/.spec-guard/native-collaboration/dist/server.js")
        report = self.run_doctor()
        self.assertEqual(report["state"], "warn")
        states = self.states(report)
        # codex-gated-wake D68: auto-approval no longer blocks wake (D66), so it is not a warning; the text is accurate.
        approval = self.find(report, "codex-approval")
        self.assertEqual(approval["state"], "ok", approval)
        self.assertIn("applies per turn and is not stored in config.toml", approval["detail"])
        self.assertIn("Woken peer turns run read-only", approval["detail"])
        self.assertNotIn("请求批准", approval["detail"] + approval["next"])
        self.assertEqual(states["wake-bindings"], "warn")
        self.assertIn("waiting", self.find(report, "wake-bindings")["detail"])
        self.assertEqual(states["old-bridges"], "warn")
        for check in report["checks"]:
            if check["state"] != "ok":
                self.assertTrue(check["next"], check)

    def test_a_binding_to_a_closed_session_warns(self):
        self.alive.clear()
        report = self.run_doctor()
        self.assertEqual(self.find(report, "wake-bindings")["state"], "warn")
        self.assertIn("not running", self.find(report, "wake-bindings")["detail"])

    def test_a_backlog_near_the_cap_warns(self):
        with sqlite3.connect(self.database) as connection:
            connection.executemany("INSERT INTO messages (to_agent, delivery_state) VALUES (?, ?)",
                                   [("reviewer", "queued")] * 80 + [("reviewer", "accepted")] * 30)
        report = self.run_doctor()
        self.assertEqual(self.find(report, "mailbox")["state"], "warn")
        self.assertIn("reviewer: 80", self.find(report, "mailbox")["detail"])

    def test_a_schema_2_mailbox_says_the_backlog_is_not_measured(self):
        with sqlite3.connect(self.database) as connection:
            connection.executescript("ALTER TABLE messages DROP COLUMN delivery_state; PRAGMA user_version = 2;")
        mailbox = self.find(self.run_doctor(), "mailbox")
        self.assertEqual(mailbox["state"], "ok")
        self.assertIn("backlog not measured", mailbox["detail"])

    def test_no_host_attached_warns(self):
        self.codex_config.write_text('approval_policy = "on-request"\n')
        self.claude_json.write_text("{}")
        report = self.run_doctor()
        self.assertEqual(self.find(report, "host-entries")["state"], "warn")

    def test_failures(self):
        cases = {
            "runtime": lambda: (self.root / "manifest.json").write_text("{}"),
            "probe": None,
            "mailbox": lambda: sqlite3.connect(self.database).execute("PRAGMA user_version = 9").connection.commit(),
            "host-entries": lambda: self.codex_config.write_text(
                codex_fragment(self.root, NODE).replace('"bridge_wait"', '"bridge_wait", "ask_codex"')),
        }
        for name, breaker in cases.items():
            with self.subTest(check=name):
                self.setUp()
                overrides = {}
                if breaker is None:
                    overrides["probe"] = lambda _root: {"state": "invalid", "diagnostic": "no tools"}
                else:
                    breaker()
                report = self.run_doctor(**overrides)
                self.assertEqual(report["state"], "fail")
                self.assertEqual(self.states(report).get(name), "fail", json.dumps(report, indent=1))

    def test_claude_deny_rules_missing_fail(self):
        self.claude_settings.write_text(json.dumps({"permissions": {"deny": []}}))
        self.assertEqual(self.find(self.run_doctor(), "host-entries")["state"], "fail")

    def test_codex_auto_approval_matches_the_bridge_rules(self):
        cases = [
            ('approval_policy = "on-request"\napprovals_reviewer = "guardian_subagent"\n', True),
            ("approval_policy = 'never'  # full auto\n", True),
            ('approval_policy = "on-request"\nsandbox_mode = "workspace-write"\n', False),
            (None, False),
            ("approvals_reviewer = guardian_subagent\n", True),
            ('approval_policy = "on-request"\n[profiles.fast]\napproval_policy = "never"\n', False),
            ('[mcp_servers.x]\napprovals_reviewer = "guardian_subagent"\n', False),
        ]
        for config, auto in cases:
            with self.subTest(config=config):
                path = self.home / "approval.toml"
                if path.exists():
                    path.unlink()
                if config is not None:
                    path.write_text(config)
                self.assertEqual(codex_auto_approval(path)[0], auto)
        path.write_text('approval_policy = "on-request"\n')
        path.chmod(0)
        self.addCleanup(path.chmod, 0o600)
        if os.getuid() != 0:
            self.assertTrue(codex_auto_approval(path)[0])

    def waiting_mailbox(self, *rows):
        """Add the columns the D77 check reads, then (id, from, to, state, minutes ago, acked) rows."""
        from datetime import datetime, timedelta, timezone
        with sqlite3.connect(self.database) as connection:
            connection.executescript("""
                ALTER TABLE agents ADD COLUMN host_app TEXT;
                ALTER TABLE messages ADD COLUMN from_agent TEXT;
                ALTER TABLE messages ADD COLUMN created_at TEXT;
                ALTER TABLE messages ADD COLUMN body TEXT;
                UPDATE agents SET host_app = 'codex' WHERE name = 'codex-one';
                UPDATE agents SET host_app = 'claude' WHERE name = 'reviewer';
            """)
            for message_id, sender, to, state, minutes, acked in rows:
                created = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                connection.execute("INSERT INTO messages (id, to_agent, delivery_state, from_agent, created_at, body) "
                                   "VALUES (?, ?, ?, ?, ?, 'secret body')", (message_id, to, state, sender, created))
                if acked:
                    connection.execute("INSERT INTO acknowledgements VALUES (?, ?)", (message_id, to))

    def test_codex_waiting_lists_what_waits_for_codex(self):
        # acceptance-030-gaps D77: the place the user can always see, whatever macOS does with banners.
        self.assertEqual(self.find(self.run_doctor(), "codex-waiting")["state"], "ok")
        self.waiting_mailbox((1, "a", "codex-one", "queued", 1, False), (2, "b", "codex-one", "accepted", 2, False),
                             (3, "a", "codex-one", "queued", 1, True), (4, "a", "codex-one", "failed", 1, False),
                             (5, "a", "codex-one", "expired", 1, False), (6, "a", "reviewer", "queued", 30, False))
        check = self.find(self.run_doctor(), "codex-waiting")
        self.assertEqual(check["state"], "ok", check)
        self.assertEqual(check["detail"], "codex-one: 2 waiting from a, b (#1, #2)")
        self.assertNotIn("secret", json.dumps(check))

    def test_codex_waiting_warns_after_ten_minutes(self):
        self.waiting_mailbox((7, "a", "codex-one", "queued", 11, False))
        check = self.find(self.run_doctor(), "codex-waiting")
        self.assertEqual(check["state"], "warn", check)
        self.assertIn("codex-one: 1 waiting from a (#7)", check["detail"])
        self.assertIn("10 minutes", check["detail"])
        self.assertIn("open that Codex task", check["next"])

    def test_notifications_check_reads_script_editor_best_effort(self):
        # acceptance-030-gaps D78: osascript notifications are attributed to Script Editor; macOS drops them silently.
        cases = [
            (prefs(SCRIPT_EDITOR_ALLOWED), "ok", "appears allowed"),
            (prefs(SCRIPT_EDITOR_NEVER_ALLOWED), "warn", "appears not allowed"),
            (prefs({**SCRIPT_EDITOR_ALLOWED, "flags": 0x200e}), "warn", "appears not allowed"),
            (prefs({"bundle-id": SCRIPT_EDITOR, "flags": 0x12802056}), "warn", "appears not allowed"),
            (prefs(), "warn", "never registered"),
            (b"not a plist", "warn", "cannot read"),
            (None, "warn", "cannot read"),
        ]
        for data, state, words in cases:
            check = self.find(self.run_doctor(notification_prefs=lambda data=data: data), "notifications")
            self.assertEqual((check["state"], words in check["detail"]), (state, True), check)
            if state == "warn":
                self.assertIn("Script Editor", check["next"])
                self.assertIn("--test-notification", check["next"])
        self.assertIn("Focus", self.find(self.run_doctor(), "notifications")["detail"])
        check = self.find(self.run_doctor(platform="linux", notification_prefs=lambda: None), "notifications")
        self.assertEqual((check["state"], "not macOS" in check["detail"]), ("ok", True), check)

    def test_notifications_turned_off_by_choice_is_ok(self):
        (self.root / "mailbox" / "notify.off").write_text("")
        check = self.find(self.run_doctor(notification_prefs=lambda: prefs()), "notifications")
        self.assertEqual((check["state"], "off by choice" in check["detail"]), ("ok", True), check)
        (self.root / "mailbox" / "notify.off").unlink()
        os.environ["AGENT_RELAY_NOTIFY"] = "off"
        self.addCleanup(os.environ.pop, "AGENT_RELAY_NOTIFY", None)
        check = self.find(self.run_doctor(notification_prefs=lambda: prefs()), "notifications")
        self.assertEqual(check["state"], "ok", check)

    def test_test_notification_runs_osascript_once_and_only_on_request(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            import subprocess
            return subprocess.CompletedProcess(command, 0, "", "")

        from unittest.mock import patch
        with patch("native_collaboration_doctor.subprocess.run", side_effect=fake_run):
            self.run_doctor()
            self.run_doctor(notification_prefs=lambda: prefs())
        self.assertFalse([c for c in calls if c and c[0] == "osascript"], "plain doctor never shows a notification")
        calls.clear()
        result = send_test_notification(run=fake_run)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "osascript")
        self.assertEqual(calls[0][-1], TEST_NOTIFICATION_TEXT)
        self.assertEqual(TEST_NOTIFICATION_TEXT, "agent-relay test notification")
        self.assertIn("Did a banner appear?", result["ask"])

    def test_cli_exit_codes(self):
        import contextlib
        import io

        def run(*extra):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["doctor", "--root", str(self.home / "missing-runtime"),
                             "--codex-config", str(self.codex_config), "--claude-json", str(self.claude_json),
                             "--claude-settings", str(self.claude_settings), "--claude-sessions", str(self.sessions),
                             *extra])
            return code, json.loads(out.getvalue())

        code, report = run()
        self.assertEqual(code, 1)
        self.assertEqual(report["state"], "fail")
        self.assertNotIn("testNotification", report)
        from unittest.mock import patch
        with patch("native_collaboration_doctor.send_test_notification",
                   return_value={"sent": True, "text": "agent-relay test notification", "ask": "Did a banner appear?"}) as sent:
            code, report = run("--test-notification")
        sent.assert_called_once()
        self.assertEqual(report["testNotification"]["sent"], True)


if __name__ == "__main__":
    unittest.main()
