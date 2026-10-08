"""upgrade-recovery D108: rollback --confirm returns to the newest previous runtime with mailbox and data."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_collaboration_runtime as runtime
from native_collaboration_runtime import NativeRuntimeError, rollback_runtime, status, upgrade_runtime
import test_runtime_upgrade
from test_runtime_upgrade import fake_run
from test_runtime_swap_guard import fail_at

COUNTS = {"acknowledgements": 1, "agents": 2, "messages": 3, "wake_jobs": 1}


class RollbackTests(unittest.TestCase):
    make_legacy_runtime = test_runtime_upgrade.RuntimeUpgradeTests.make_legacy_runtime

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-rollback-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve() / "relay"
        self.home.mkdir(mode=0o700)
        self.root = self.home / "runtime"
        self.backups = self.home / "backups"
        self.make_legacy_runtime()
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            self.upgraded = upgrade_runtime(self.root, backups=self.backups, running=lambda _root: 0)
        self.assertNotEqual((self.root / "dist" / "server.js").read_text(), "old server\n")

    def rollback(self, **kwargs):
        kwargs.setdefault("running", lambda _root: 0)
        return rollback_runtime(self.root, backups=self.backups, **kwargs)

    def test_rollback_returns_to_the_previous_runtime_with_the_history(self):
        self.assertIn("rollback --confirm", self.upgraded["rollback"])
        new_server = (self.root / "dist" / "server.js").read_text()
        result = self.rollback()
        self.assertEqual(result["state"], "rolled-back")
        self.assertEqual(Path(result["previous"]), Path(self.upgraded["previous"]))
        self.assertEqual(status(self.root)["state"], "ready")
        self.assertEqual((self.root / "dist" / "server.js").read_text(), "old server\n")
        self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")
        self.assertEqual(runtime._mailbox_counts(self.root / "mailbox" / "bridge.sqlite"), COUNTS)
        rolled = Path(result["rolledBack"])
        self.assertTrue(rolled.name.startswith("runtime.rolled-back-"))
        self.assertEqual((rolled / "dist" / "server.js").read_text(), new_server, "the newer build is kept")
        self.assertTrue((Path(result["backup"]) / "runtime-mailbox" / "bridge.sqlite").is_file())
        self.assertIn("schema", result["caveat"])
        self.assertFalse(Path(self.upgraded["previous"]).exists())
        self.assertFalse(runtime._journal_path(self.root).exists())

    def test_the_newest_previous_is_used(self):
        older = self.home / "runtime.previous-20200101T000000Z"
        older.mkdir()
        self.assertEqual(Path(self.rollback()["previous"]), Path(self.upgraded["previous"]))
        self.assertTrue(older.is_dir(), "other previous runtimes are left alone")

    def test_rollback_refuses_without_a_previous_while_running_or_interrupted(self):
        Path(self.upgraded["previous"]).rename(self.home / "elsewhere")
        with self.assertRaisesRegex(NativeRuntimeError, "no previous runtime"):
            self.rollback()
        (self.home / "elsewhere").rename(self.upgraded["previous"])
        with self.assertRaisesRegex(NativeRuntimeError, "running"):
            self.rollback(running=lambda _root: 1)
        runtime._write_journal(self.root, {"kind": "upgrade", "step": "moving-history", "runtime": str(self.root),
                                           "incoming": str(self.home / "x"), "outgoing": None, "park": str(self.home / "y")})
        with self.assertRaisesRegex(NativeRuntimeError, "recover --confirm"):
            self.rollback()

    def test_a_failure_at_each_rollback_step_keeps_the_upgraded_runtime(self):
        for step in runtime.SWAP_STEPS:
            with self.subTest(step):
                self.setUp()
                new_server = (self.root / "dist" / "server.js").read_text()
                with patch("native_collaboration_runtime._write_journal", side_effect=fail_at(step)), \
                        self.assertRaisesRegex(NativeRuntimeError, "rolled back"):
                    self.rollback()
                self.assertEqual((self.root / "dist" / "server.js").read_text(), new_server)
                self.assertEqual(runtime._mailbox_counts(self.root / "mailbox" / "bridge.sqlite"), COUNTS)
                previous = Path(self.upgraded["previous"])
                self.assertEqual((previous / "dist" / "server.js").read_text(), "old server\n",
                                 "the previous runtime keeps its name and build")
                self.assertFalse(runtime._journal_path(self.root).exists())

    def test_a_killed_rollback_is_recovered(self):
        # A real kill leaves the journal; lay that out by stopping before the guard can act.
        journal_writes = []
        original = runtime._write_journal

        def record(root, journal):
            original(root, journal)
            journal_writes.append(dict(journal))
            if journal["step"] == "promoting":
                raise SystemExit("killed")
        with patch("native_collaboration_runtime._write_journal", side_effect=record), \
                patch("native_collaboration_runtime._put_back", side_effect=SystemExit("killed again")), \
                self.assertRaises(SystemExit):
            self.rollback()
        self.assertEqual(status(self.root)["state"], "interrupted")
        self.assertEqual(status(self.root)["journal"]["kind"], "rollback")
        result = runtime.recover_runtime(self.root, running=lambda _root: 0)
        self.assertEqual(result["state"], "recovered")
        self.assertNotEqual((self.root / "dist" / "server.js").read_text(), "old server\n", "back to the upgraded one")
        self.assertEqual((Path(self.upgraded["previous"]) / "dist" / "server.js").read_text(), "old server\n")
        self.assertEqual(runtime._mailbox_counts(self.root / "mailbox" / "bridge.sqlite"), COUNTS)

    def test_cli_needs_confirmation(self):
        environment = {"AGENT_RELAY_HOME": str(self.home)}
        with patch.dict(os.environ, environment), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as refused:
            runtime.main(["rollback"])
        self.assertEqual(refused.exception.code, 2)
        out = io.StringIO()
        with patch.dict(os.environ, environment), contextlib.redirect_stdout(out), \
                patch("native_collaboration_runtime._servers_running", return_value=0):
            self.assertEqual(runtime.main(["rollback", "--confirm"]), 0)
        self.assertEqual(json.loads(out.getvalue())["state"], "rolled-back")


if __name__ == "__main__":
    unittest.main()
