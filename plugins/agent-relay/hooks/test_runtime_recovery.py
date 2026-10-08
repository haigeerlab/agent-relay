"""upgrade-recovery: an interrupted runtime swap is reported and rolled back by `recover --confirm` (D104, D105, D109)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

import native_collaboration_runtime as runtime
from native_collaboration_runtime import NativeRuntimeError, recover_runtime, status, uninstall_runtime, upgrade_runtime
import test_runtime_upgrade

COUNTS = {"acknowledgements": 1, "agents": 2, "messages": 3, "wake_jobs": 1}


class RecoveryTests(unittest.TestCase):
    make_legacy_runtime = test_runtime_upgrade.RuntimeUpgradeTests.make_legacy_runtime

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-recover-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve() / "relay"
        self.home.mkdir(mode=0o700)
        self.root = self.home / "runtime"
        self.make_legacy_runtime()
        self.stamp = "20261008T120000Z"
        self.stage = self.home / f".runtime-upgrade-{self.stamp}-abc123"
        self.previous = self.home / f"runtime.previous-{self.stamp}"

    def new_build(self, path: Path) -> None:
        path.mkdir(mode=0o700)
        (path / "dist").mkdir()
        (path / "dist" / "server.js").write_text("new server\n")

    def journal(self, kind: str, step: str, *, incoming: Path, outgoing: Path | None, park: Path) -> None:
        runtime._write_journal(self.root, {
            "kind": kind, "stamp": self.stamp, "runtime": str(self.root), "incoming": str(incoming),
            "outgoing": None if outgoing is None else str(outgoing), "park": str(park), "counts": COUNTS, "step": step})

    def upgrade_killed_at(self, step: str, *, moved=("mailbox", "data"), retired=False, promoted=False) -> Path:
        """Lay the directories out as an upgrade killed during `step` leaves them, journal included."""
        park = self.home / f".runtime-upgrade-failed-{self.stamp}"
        self.new_build(self.stage)
        self.journal("upgrade", step, incoming=self.stage, outgoing=self.previous, park=park)
        for name in moved:
            (self.root / name).rename(self.stage / name)
        if retired:
            self.root.rename(self.previous)
        if promoted:
            self.stage.rename(self.root)
        return park

    def assert_restored(self, park: Path) -> None:
        self.assertEqual(status(self.root)["state"], "ready")
        self.assertEqual((self.root / "dist" / "server.js").read_text(), "old server\n")
        self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")
        self.assertEqual(runtime._mailbox_counts(self.root / "mailbox" / "bridge.sqlite"), COUNTS)
        self.assertEqual((park / "dist" / "server.js").read_text(), "new server\n", "the half-built runtime is kept")
        self.assertFalse(runtime._journal_path(self.root).exists())
        self.assertFalse(self.previous.exists())
        self.assertFalse(self.stage.exists())

    def test_each_interrupted_upgrade_step_is_reported_refused_and_recovered(self):
        cases = {
            "moving-history (half moved)": dict(step="moving-history", moved=("mailbox",)),
            "retiring-runtime (not yet renamed)": dict(step="retiring-runtime"),
            "retiring-runtime (renamed)": dict(step="retiring-runtime", retired=True),
            "promoting (no runtime directory)": dict(step="promoting", retired=True),
            "promoting (stage already promoted)": dict(step="promoting", retired=True, promoted=True),
            "verifying": dict(step="verifying", retired=True, promoted=True),
        }
        for name, case in cases.items():
            with self.subTest(name):
                self.setUp()
                park = self.upgrade_killed_at(**case)
                report = status(self.root)
                self.assertEqual(report["state"], "interrupted")
                self.assertEqual(report["journal"]["kind"], "upgrade")
                self.assertIn("recover --confirm", report["next"])
                with self.assertRaisesRegex(NativeRuntimeError, "recover --confirm"):
                    upgrade_runtime(self.root, running=lambda _root: 0)
                with self.assertRaisesRegex(NativeRuntimeError, "recover --confirm"):
                    uninstall_runtime(self.root, running=lambda _root: 0)
                result = recover_runtime(self.root, running=lambda _root: 0)
                self.assertEqual(result["state"], "recovered")
                self.assertEqual(Path(result["parked"]), park)
                self.assert_restored(park)

    def test_an_interrupted_reinstall_goes_back_to_the_uninstalled_runtime(self):
        for name, (moved, removed, promoted) in {
            "moving-history": (("mailbox",), False, False),
            "retiring-runtime": (("mailbox", "data"), True, False),
            "promoting": (("mailbox", "data"), True, True),
        }.items():
            with self.subTest(name):
                self.setUp()
                for entry in self.root.iterdir():
                    if entry.name not in ("mailbox", "data"):
                        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
                self.assertEqual(status(self.root)["state"], "uninstalled")
                stage = self.home / f".runtime-reinstall-{self.stamp}-abc123"
                park = self.home / f".runtime-reinstall-failed-{self.stamp}"
                self.new_build(stage)
                self.journal("reinstall", {"moving-history": "moving-history", "retiring-runtime": "retiring-runtime",
                                           "promoting": "promoting"}[name], incoming=stage, outgoing=None, park=park)
                for item in moved:
                    (self.root / item).rename(stage / item)
                if removed:
                    self.root.rmdir()
                if promoted:
                    stage.rename(self.root)
                self.assertEqual(status(self.root)["state"], "interrupted")
                self.assertEqual(recover_runtime(self.root, running=lambda _root: 0)["state"], "recovered")
                self.assertEqual(status(self.root)["state"], "uninstalled")
                self.assertEqual(runtime._mailbox_counts(self.root / "mailbox" / "bridge.sqlite"), COUNTS)
                self.assertEqual((self.root / "data" / "keep.txt").read_text(), "data kept\n")
                self.assertEqual((park / "dist" / "server.js").read_text(), "new server\n")
                self.assertFalse(stage.exists())
                self.assertFalse(runtime._journal_path(self.root).exists())

    def test_recover_refuses_without_a_journal_or_while_a_bridge_runs(self):
        with self.assertRaisesRegex(NativeRuntimeError, "nothing to recover"):
            recover_runtime(self.root, running=lambda _root: 0)
        self.upgrade_killed_at("retiring-runtime", retired=True)
        with self.assertRaisesRegex(NativeRuntimeError, "running"):
            recover_runtime(self.root, running=lambda _root: 1)
        self.assertEqual(status(self.root)["state"], "interrupted", "a refusal changes nothing")

    def test_a_count_mismatch_keeps_the_journal(self):
        self.upgrade_killed_at("verifying", retired=True, promoted=True)
        with patch("native_collaboration_runtime._mailbox_counts", return_value={"messages": 2}), \
                self.assertRaisesRegex(NativeRuntimeError, "row counts"):
            recover_runtime(self.root, running=lambda _root: 0)
        self.assertTrue(runtime._journal_path(self.root).exists())

    def test_the_journal_is_private_and_written_whole(self):
        self.upgrade_killed_at("moving-history", moved=())
        path = runtime._journal_path(self.root)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(json.loads(path.read_text())["step"], "moving-history")
        self.assertEqual([p.name for p in self.home.iterdir() if p.name.startswith("runtime-swap.json.")], [])

    def test_cli_recover_needs_confirmation_and_status_exits_1_when_interrupted(self):
        self.upgrade_killed_at("retiring-runtime", retired=True)
        environment = {"AGENT_RELAY_HOME": str(self.home)}
        with patch.dict(os.environ, environment), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as refused:
            runtime.main(["recover"])
        self.assertEqual(refused.exception.code, 2)
        out = io.StringIO()
        with patch.dict(os.environ, environment), contextlib.redirect_stdout(out):
            self.assertEqual(runtime.main(["status"]), 1)
        self.assertEqual(json.loads(out.getvalue())["state"], "interrupted")
        out = io.StringIO()
        with patch.dict(os.environ, environment), contextlib.redirect_stdout(out), \
                patch("native_collaboration_runtime._servers_running", return_value=0):
            self.assertEqual(runtime.main(["recover", "--confirm"]), 0)
        self.assertEqual(json.loads(out.getvalue())["state"], "recovered")
        self.assertEqual(status(self.root)["state"], "ready")


if __name__ == "__main__":
    unittest.main()
