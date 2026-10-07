"""uninstall --confirm removes the runtime build and keeps the message history (safe-uninstall D47)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from native_collaboration_doctor import doctor
from native_collaboration_runtime import (NativeRuntimeError, install_runtime, main, status, uninstall_runtime)
from test_runtime_upgrade import fake_run


class RuntimeUninstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-uninstall-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve() / "relay"
        self.home.mkdir(mode=0o700)
        self.root = self.home / "runtime"
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            install_runtime(self.root)
        database = self.root / "mailbox" / "bridge.sqlite"
        with sqlite3.connect(database) as connection:
            connection.executescript("""
                PRAGMA user_version = 5;
                CREATE TABLE agents (name TEXT PRIMARY KEY, retired_at TEXT);
                CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT);
                CREATE TABLE acknowledgements (message_id INTEGER, agent TEXT);
                CREATE TABLE wake_jobs (id INTEGER PRIMARY KEY, state TEXT);
                CREATE TABLE wake_targets (agent TEXT PRIMARY KEY, target TEXT);
                INSERT INTO agents VALUES ('a', NULL);
                INSERT INTO messages VALUES (1, 'history one'), (2, 'history two');
            """)
        database.chmod(0o600)
        (self.root / "mailbox" / "backups" / "bridge-daily-2026-10-07.sqlite").write_bytes(b"backup")
        (self.root / "mailbox" / "backups" / "bridge-daily-2026-10-07.sqlite").chmod(0o600)
        (self.root / "data" / "keep.txt").write_text("data kept\n")
        self.history = database.read_bytes()

    def test_the_build_goes_and_mailbox_backups_and_data_stay(self):
        self.assertEqual(status(self.root)["state"], "ready")
        result = uninstall_runtime(self.root, running=lambda _root: 0)
        self.assertEqual(result["state"], "uninstalled")
        self.assertEqual(result["history"], str(self.root / "mailbox"))
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["data", "mailbox"])
        self.assertEqual((self.root / "mailbox" / "bridge.sqlite").read_bytes(), self.history)
        self.assertTrue((self.root / "mailbox" / "backups" / "bridge-daily-2026-10-07.sqlite").exists())
        self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")
        self.assertEqual(status(self.root), {"state": "uninstalled", "history": str(self.root / "mailbox")})
        self.assertEqual(uninstall_runtime(self.root, running=lambda _root: 0)["state"], "uninstalled", "idempotent")

    def test_refused_while_a_bridge_server_runs(self):
        with self.assertRaisesRegex(NativeRuntimeError, "running"):
            uninstall_runtime(self.root, running=lambda _root: 1)
        self.assertEqual(status(self.root)["state"], "ready")

    def test_install_rebuilds_around_the_kept_history(self):
        uninstall_runtime(self.root, running=lambda _root: 0)
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            result = install_runtime(self.root)
        self.assertEqual(result["state"], "ready")
        self.assertEqual((self.root / "mailbox" / "bridge.sqlite").read_bytes(), self.history)
        self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")
        self.assertTrue((self.root / "dist" / "server.js").exists())
        self.assertEqual(sorted(path.name for path in self.home.iterdir()), ["runtime"], "no stage left behind")

    def test_doctor_reports_an_uninstalled_runtime_with_its_history(self):
        uninstall_runtime(self.root, running=lambda _root: 0)
        report = doctor(self.root, home=self.home, processes=lambda: [], alive=lambda _pid: False)
        runtime = next(check for check in report["checks"] if check["check"] == "runtime")
        self.assertEqual(runtime["state"], "warn")
        self.assertIn(str(self.root / "mailbox"), runtime["detail"])

    def test_cli_needs_confirmation_and_reports_uninstalled(self):
        def run(*extra):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    patch("native_collaboration_runtime._servers_running", return_value=0):
                try:
                    code = main(["uninstall", "--root", str(self.root), *extra])
                except SystemExit as error:
                    code = error.code
            return code, out.getvalue() + err.getvalue()

        code, output = run()
        self.assertEqual(code, 2)
        self.assertIn("--confirm", output)
        self.assertEqual(status(self.root)["state"], "ready")
        code, output = run("--confirm")
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["state"], "uninstalled")


if __name__ == "__main__":
    unittest.main()
