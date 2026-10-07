"""upgrade --confirm moves an installed runtime to the plugin's bridge without losing the mailbox (D26)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import native_collaboration_runtime as runtime
from native_collaboration_runtime import BRIDGE_COMMIT, NativeRuntimeError, status, upgrade_runtime


def fake_run(command, **kwargs):
    if command[:2] == ["node", "--version"]:
        return subprocess.CompletedProcess(command, 0, "v22.5.0\n", "")
    if command[:3] == ["npm", "run", "build"]:
        (Path(kwargs["cwd"]) / "dist").mkdir()
        (Path(kwargs["cwd"]) / "dist" / "server.js").write_text("server\n")
    return subprocess.CompletedProcess(command, 0, "", "")


class RuntimeUpgradeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-upgrade-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve() / "relay"
        self.home.mkdir(mode=0o700)
        self.root = self.home / "runtime"
        self.backups = self.home / "backups"
        self.make_legacy_runtime()

    def make_legacy_runtime(self):
        """A runtime installed from upstream by git, with a v2 mailbox holding real rows."""
        self.root.mkdir(mode=0o700)
        for sub in ("mailbox", "mailbox/backups", "data"):
            (self.root / sub).mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "dist" / "server.js").write_text("old server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        (self.root / "data" / "keep.txt").write_text("data kept\n")
        database = self.root / "mailbox" / "bridge.sqlite"
        with sqlite3.connect(database) as connection:
            connection.executescript("""
                PRAGMA user_version = 2;
                CREATE TABLE agents (name TEXT PRIMARY KEY);
                CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT);
                CREATE TABLE acknowledgements (message_id INTEGER, agent TEXT);
                CREATE TABLE wake_jobs (id INTEGER PRIMARY KEY, state TEXT);
                INSERT INTO agents VALUES ('a'), ('b');
                INSERT INTO messages VALUES (1, 'one'), (2, 'two'), (3, 'three');
                INSERT INTO acknowledgements VALUES (1, 'b');
                INSERT INTO wake_jobs VALUES (1, 'read');
            """)
        database.chmod(0o600)

    def upgrade(self, **kwargs):
        kwargs.setdefault("running", lambda _root: 0)
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            return upgrade_runtime(self.root, backups=self.backups, **kwargs)

    def test_upgrade_swaps_in_the_plugin_bridge_and_keeps_the_mailbox(self):
        self.assertFalse(status(self.root)["bridge"]["current"])
        before = (self.root / "mailbox" / "bridge.sqlite").read_bytes()
        result = self.upgrade()
        self.assertEqual(result["state"], "upgraded")
        after = status(self.root)
        self.assertEqual(after["state"], "ready")
        self.assertEqual(after["bridge"]["source"], "vendored")
        self.assertTrue(after["bridge"]["current"])
        self.assertEqual((self.root / "mailbox" / "bridge.sqlite").read_bytes(), before)
        self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")
        self.assertEqual(result["counts"], {"acknowledgements": 1, "agents": 2, "messages": 3, "wake_jobs": 1})
        previous = Path(result["previous"])
        self.assertEqual((previous / "dist" / "server.js").read_text(), "old server\n")
        backup = Path(result["backup"])
        self.assertEqual((backup / "runtime-mailbox" / "bridge.sqlite").read_bytes(), before)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertIn("rollback", result)

    def test_upgrade_refuses_while_a_bridge_server_of_this_runtime_runs(self):
        with self.assertRaisesRegex(NativeRuntimeError, "running"):
            self.upgrade(running=lambda _root: 2)
        self.assertEqual(status(self.root)["bridge"]["source"], "upstream-git")
        self.assertFalse(self.backups.exists())

    def test_a_current_runtime_is_left_alone(self):
        self.upgrade()
        again = self.upgrade()
        self.assertEqual(again["state"], "current")

    def test_a_failed_build_changes_nothing(self):
        def failing(command, **kwargs):
            if command[:3] == ["npm", "run", "build"]:
                return subprocess.CompletedProcess(command, 1, "", "boom")
            return fake_run(command, **kwargs)
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        with patch("native_collaboration_runtime.subprocess.run", side_effect=failing), \
                self.assertRaises(NativeRuntimeError):
            upgrade_runtime(self.root, backups=self.backups, running=lambda _root: 0)
        self.assertEqual(sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")), before)
        self.assertEqual(status(self.root)["bridge"]["source"], "upstream-git")
        self.assertEqual([p.name for p in self.home.iterdir() if p.name.startswith(".runtime-upgrade")], [])

    def test_a_failed_verification_rolls_the_swap_back(self):
        with patch("native_collaboration_runtime._mailbox_counts",
                   side_effect=[{"messages": 3}, {"messages": 2}]), \
                self.assertRaisesRegex(NativeRuntimeError, "rolled back"):
            self.upgrade()
        self.assertEqual(status(self.root)["bridge"]["source"], "upstream-git")
        self.assertEqual((self.root / "dist" / "server.js").read_text(), "old server\n")
        self.assertTrue((self.root / "mailbox" / "bridge.sqlite").is_file())
        self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")

    def test_cli_needs_confirmation(self):
        with patch.dict(os.environ, {"AGENT_RELAY_HOME": str(self.home)}), \
                patch("sys.stdout"), self.assertRaises(SystemExit) as caught:
            runtime.main(["upgrade"])
        self.assertEqual(caught.exception.code, 2)


    def test_the_backups_directory_ends_private_even_if_it_existed_open(self):
        self.backups.mkdir(mode=0o755)
        self.backups.chmod(0o755)
        self.assertEqual(self.upgrade()["state"], "upgraded")
        self.assertEqual(stat.S_IMODE(self.backups.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
