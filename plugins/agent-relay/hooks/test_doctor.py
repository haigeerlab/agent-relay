"""doctor reports agent-relay's health on this Mac, read only (ops-commands D42)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import sys
import unittest

from native_collaboration_adapters import CLAUDE_SERVER_NAME, codex_fragment
from native_collaboration_doctor import codex_auto_approval, doctor
from native_collaboration_runtime import BRIDGE_COMMIT, BRIDGE_SOURCE, DENIED_TOOLS, bridge_tree, main

NODE = Path(sys.executable)


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
                       processes=lambda: self.processes, alive=lambda pid: pid in self.alive)
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

    def test_warnings_name_the_problem_and_the_next_step(self):
        self.codex_config.write_text('approvals_reviewer = "guardian_subagent"\n\n' + codex_fragment(self.root, NODE))
        self.session("claude-live", "waiting")
        self.processes.append("node /Users/x/.spec-guard/native-collaboration/dist/server.js")
        report = self.run_doctor()
        self.assertEqual(report["state"], "warn")
        states = self.states(report)
        self.assertEqual(states["codex-approval"], "warn")
        self.assertIn("请求批准", self.find(report, "codex-approval")["next"])
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


if __name__ == "__main__":
    unittest.main()
