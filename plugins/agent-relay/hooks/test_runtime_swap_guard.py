"""upgrade-recovery D106, D107: a failure at any step of an upgrade or reinstall puts the runtime back at once,
and a stage directory is only ever removed by the call that created it."""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import native_collaboration_runtime as runtime
from native_collaboration_runtime import NativeRuntimeError, install_runtime, status, upgrade_runtime
import test_runtime_upgrade
from test_runtime_upgrade import fake_run

COUNTS = {"acknowledgements": 1, "agents": 2, "messages": 3, "wake_jobs": 1}
REAL_WRITE = runtime._write_journal
REAL_RENAME = Path.rename


def fail_at(step):
    """Write the journal, then fail as the step is about to move anything."""
    def write(root, journal):
        REAL_WRITE(root, journal)
        if journal["step"] == step:
            raise RuntimeError(f"injected at {step}")
    return write


class SwapGuardTests(unittest.TestCase):
    make_legacy_runtime = test_runtime_upgrade.RuntimeUpgradeTests.make_legacy_runtime

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-swap-guard-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve() / "relay"
        self.home.mkdir(mode=0o700)
        self.root = self.home / "runtime"
        self.backups = self.home / "backups"
        self.make_legacy_runtime()

    def upgrade(self):
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            return upgrade_runtime(self.root, backups=self.backups, running=lambda _root: 0)

    def assert_old_runtime_back(self):
        self.assertEqual(status(self.root)["state"], "ready")
        self.assertEqual((self.root / "dist" / "server.js").read_text(), "old server\n")
        self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")
        self.assertEqual(runtime._mailbox_counts(self.root / "mailbox" / "bridge.sqlite"), COUNTS)
        self.assertFalse(runtime._journal_path(self.root).exists())
        self.assertEqual(sorted(p.name for p in self.home.glob(".runtime-upgrade-*") if "-failed-" not in p.name), [])
        self.assertEqual(list(self.home.glob("runtime.previous-*")), [])

    def test_a_failure_at_each_upgrade_step_puts_the_old_runtime_back(self):
        for step in runtime.SWAP_STEPS:
            with self.subTest(step):
                self.setUp()
                with patch("native_collaboration_runtime._write_journal", side_effect=fail_at(step)), \
                        self.assertRaisesRegex(NativeRuntimeError, "rolled back"):
                    self.upgrade()
                self.assert_old_runtime_back()
                parked = list(self.home.glob(".runtime-upgrade-failed-*"))
                self.assertEqual(len(parked), 1, "the new build is kept for inspection")

    def test_a_failure_half_way_through_moving_the_history(self):
        def rename(path, target):
            if Path(path).name == "data" and ".runtime-upgrade-" in str(target):
                raise OSError("injected while moving data")
            return REAL_RENAME(path, target)
        with patch.object(Path, "rename", rename), self.assertRaisesRegex(NativeRuntimeError, "rolled back"):
            self.upgrade()
        self.assert_old_runtime_back()

    def test_a_failing_final_rename_puts_the_old_runtime_back(self):
        def rename(path, target):
            if Path(target) == self.root and ".runtime-upgrade-" in Path(path).name:
                raise OSError("injected final rename")
            return REAL_RENAME(path, target)
        with patch.object(Path, "rename", rename), self.assertRaisesRegex(NativeRuntimeError, "rolled back"):
            self.upgrade()
        self.assert_old_runtime_back()

    def uninstall_build(self):
        for entry in self.root.iterdir():
            if entry.name not in ("mailbox", "data"):
                shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
        self.assertEqual(status(self.root)["state"], "uninstalled")

    def reinstall(self):
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            return install_runtime(self.root)

    def test_a_failure_at_each_reinstall_step_keeps_the_uninstalled_history(self):
        for step in runtime.SWAP_STEPS:
            with self.subTest(step):
                self.setUp()
                self.uninstall_build()
                with patch("native_collaboration_runtime._write_journal", side_effect=fail_at(step)), \
                        self.assertRaisesRegex(NativeRuntimeError, "rolled back"):
                    self.reinstall()
                self.assertEqual(status(self.root)["state"], "uninstalled")
                self.assertEqual(runtime._mailbox_counts(self.root / "mailbox" / "bridge.sqlite"), COUNTS)
                self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")
                self.assertFalse(runtime._journal_path(self.root).exists())

    def test_a_reinstall_never_removes_a_directory_it_did_not_create(self):
        self.uninstall_build()
        stamp = "20261008T120000Z"
        theirs = self.home / f".runtime-reinstall-{stamp}"  # the name the old code would have used this second
        theirs.mkdir()
        (theirs / "marker").write_text("someone else's\n")

        def failing(command, **kwargs):
            if command[:3] == ["npm", "run", "build"]:
                return runtime.subprocess.CompletedProcess(command, 1, "", "boom")
            return fake_run(command, **kwargs)
        with patch("time.strftime", return_value=stamp), \
                patch("native_collaboration_runtime.subprocess.run", side_effect=failing), \
                self.assertRaises(NativeRuntimeError):
            install_runtime(self.root)
        self.assertEqual((theirs / "marker").read_text(), "someone else's\n")
        self.assertEqual(status(self.root)["state"], "uninstalled")

    def test_a_journal_that_cannot_be_written_leaves_nothing_behind(self):
        with patch("native_collaboration_runtime._write_journal", side_effect=OSError("disk full")), \
                self.assertRaisesRegex(OSError, "disk full"):
            self.upgrade()
        self.assertEqual((self.root / "dist" / "server.js").read_text(), "old server\n")
        self.assertEqual(list(self.home.glob(".runtime-upgrade-*")), [], "this call's own stage is removed")

    def test_successful_upgrade_and_reinstall_leave_no_journal(self):
        self.assertEqual(self.upgrade()["state"], "upgraded")
        self.assertFalse(runtime._journal_path(self.root).exists())
        self.setUp()
        self.uninstall_build()
        self.assertEqual(self.reinstall()["state"], "ready")
        self.assertFalse(runtime._journal_path(self.root).exists())


if __name__ == "__main__":
    unittest.main()
