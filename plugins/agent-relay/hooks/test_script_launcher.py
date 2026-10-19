"""script-access D240: the launcher at <state home>/bin/agent-relay that scripts and launchd run."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from native_collaboration_doctor import _script_launcher
from native_collaboration_runtime import (install_runtime, launcher_path, rollback_runtime, uninstall_runtime,
                                          upgrade_runtime, write_launcher)
from test_runtime_upgrade import fake_run as upgrade_fake_run

NODE = shutil.which("node")


def fake_run(command, **kwargs):
    """The upgrade tests' fake build, accepting the absolute node the launcher needs."""
    if len(command) >= 2 and command[1] == "--version" and command[0].endswith("node"):
        return subprocess.CompletedProcess(command, 0, "v22.5.0\n", "")
    return upgrade_fake_run(command, **kwargs)


class ScriptLauncherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-launcher-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve() / "relay"
        self.home.mkdir(mode=0o700)
        self.root = self.home / "runtime"
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            self.installed = install_runtime(self.root, node=NODE or "node")

    def fake_cli(self, text: str = "") -> None:
        """A stand-in dist/cli.js that echoes its arguments and the mailbox it was given."""
        (self.root / "dist" / "cli.js").write_text(
            "console.log(JSON.stringify({args: process.argv.slice(2), db: process.env.BRIDGE_DB_PATH, "
            "data: process.env.XDG_DATA_HOME}))\n" + text, encoding="utf-8")

    def test_install_writes_a_private_launcher_with_absolute_paths(self):
        path = launcher_path(self.root)
        self.assertEqual(path, self.home / "bin" / "agent-relay")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        self.assertIn(str(self.root), text)
        self.assertIn(str(Path(NODE).resolve()) if NODE else "", text)
        self.assertEqual(self.installed["launcher"]["path"], str(path))

    @unittest.skipUnless(NODE, "needs node on PATH to resolve")
    def test_launcher_runs_with_only_usr_bin_and_bin_on_path(self):
        self.fake_cli()
        result = subprocess.run([str(launcher_path(self.root)), "agents"], capture_output=True, text=True,
                                env={"PATH": "/usr/bin:/bin", "HOME": str(self.home)}, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        printed = json.loads(result.stdout)
        self.assertEqual(printed["args"], ["agents"])
        self.assertEqual(printed["db"], str(self.root / "mailbox" / "bridge.sqlite"))
        self.assertEqual(printed["data"], str(self.root / "data"))

    def test_launcher_refuses_with_one_sentence_when_the_runtime_is_gone_or_mid_swap(self):
        launcher = launcher_path(self.root)
        (self.home / "runtime-swap.json").write_text("{}", encoding="utf-8")
        mid = subprocess.run([str(launcher), "agents"], capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin"}, timeout=30)
        self.assertNotEqual(mid.returncode, 0)
        self.assertEqual(len(mid.stderr.strip().splitlines()), 1)
        self.assertIn("upgrade", mid.stderr)
        (self.home / "runtime-swap.json").unlink()
        (self.root / "dist" / "cli.js").unlink(missing_ok=True)
        gone = subprocess.run([str(launcher), "agents"], capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin"}, timeout=30)
        self.assertNotEqual(gone.returncode, 0)
        self.assertEqual(len(gone.stderr.strip().splitlines()), 1)
        self.assertIn("not installed", gone.stderr)

    def test_write_refuses_a_node_it_cannot_resolve(self):
        result = write_launcher(self.root, node="definitely-not-a-node-binary")
        self.assertFalse(result["ok"])
        self.assertIn("node", result["diagnostic"])

    def test_uninstall_removes_the_launcher(self):
        uninstall_runtime(self.root, running=lambda _root: 0)
        self.assertFalse(launcher_path(self.root).exists())

    def test_upgrade_and_rollback_rewrite_the_launcher(self):
        launcher = launcher_path(self.root)
        launcher.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        (self.root / "manifest.json").write_text(json.dumps({**manifest, "tree": "0" * 64}))
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            upgraded = upgrade_runtime(self.root, node=NODE or "node", backups=self.home / "backups",
                                       running=lambda _root: 0)
        self.assertEqual(upgraded["state"], "upgraded")
        self.assertIn(str(self.root), launcher.read_text(encoding="utf-8"))
        self.assertEqual(upgraded["launcher"]["path"], str(launcher))
        launcher.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
        rolled = rollback_runtime(self.root, backups=self.home / "backups", running=lambda _root: 0)
        self.assertEqual(rolled["state"], "rolled-back")
        self.assertIn(str(self.root), launcher.read_text(encoding="utf-8"))

    def test_doctor_check_reports_the_launcher(self):
        self.assertEqual(_script_launcher(self.root)["state"], "ok")
        launcher = launcher_path(self.root)
        launcher.chmod(0o755)
        self.assertEqual(_script_launcher(self.root)["state"], "warn")
        launcher.chmod(0o700)
        launcher.write_text(launcher.read_text(encoding="utf-8").replace(str(self.root), "/elsewhere/runtime"),
                            encoding="utf-8")
        self.assertEqual(_script_launcher(self.root)["state"], "warn")
        launcher.unlink()
        missing = _script_launcher(self.root)
        self.assertEqual(missing["state"], "warn")
        self.assertIn("upgrade --confirm", missing["next"])



class LauncherReviewFixTests(unittest.TestCase):
    """Round-2 post-merge review of #149 (#9193)."""

    setUp = ScriptLauncherTests.setUp

    @unittest.skipUnless(NODE, "needs node on PATH")
    def test_a_symlinked_node_is_kept_as_found_not_resolved(self):
        link_dir = self.home / "linked-bin"
        link_dir.mkdir()
        link = link_dir / "node"
        link.symlink_to(Path(NODE).resolve())
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            result = write_launcher(self.root, node=str(link))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["node"], str(link))
        self.assertIn(f"NODE={link}", launcher_path(self.root).read_text(encoding="utf-8"))

    def test_the_temporary_file_is_unique_per_process(self):
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run), \
                patch("native_collaboration_runtime.Path.replace", autospec=True) as replace:
            write_launcher(self.root, node=NODE or "node")
        temporary = replace.call_args[0][0]
        self.assertIn(str(os.getpid()), temporary.name)
        self.assertNotEqual(temporary.name, ".agent-relay.tmp")

    @unittest.skipUnless(NODE, "needs node on PATH")
    def test_rollback_keeps_the_node_the_old_launcher_named(self):
        recorded = self.home / "recorded-bin" / "node"
        recorded.parent.mkdir()
        recorded.symlink_to(Path(NODE).resolve())
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            write_launcher(self.root, node=str(recorded))
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        (self.root / "manifest.json").write_text(json.dumps({**manifest, "tree": "0" * 64}))
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            upgrade_runtime(self.root, node=str(recorded), backups=self.home / "backups", running=lambda _root: 0)
            rolled = rollback_runtime(self.root, backups=self.home / "backups", running=lambda _root: 0)
        self.assertEqual(rolled["launcher"]["node"], str(recorded))
        self.assertIn("ok", rolled["launcher"])

    def test_main_says_on_stderr_when_the_launcher_was_not_written(self):
        import contextlib
        import io
        from native_collaboration_runtime import launcher_warning
        self.assertIsNone(launcher_warning({"state": "ready", "launcher": {"ok": True}}))
        self.assertIsNone(launcher_warning({"state": "ready"}))
        text = launcher_warning({"state": "upgraded", "launcher": {"ok": False, "path": "/x/bin/agent-relay",
                                                                   "diagnostic": "no executable node"}})
        self.assertIn("/x/bin/agent-relay", text)
        self.assertIn("no executable node", text)


if __name__ == "__main__":
    unittest.main()
