#!/usr/bin/env python3
"""Packaging: consistent manifests, the interface marker Spec Guard reads, and the read-only status command."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from native_collaboration_runtime import BRIDGE_COMMIT

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ManifestTests(unittest.TestCase):
    def test_both_host_manifests_agree_and_the_marketplace_lists_only_this_plugin(self):
        claude = load(PLUGIN / ".claude-plugin" / "plugin.json")
        codex = load(PLUGIN / ".codex-plugin" / "plugin.json")
        for field in ("name", "version", "description"):
            self.assertEqual(claude[field], codex[field], field)
        self.assertEqual(claude["name"], "agent-relay")
        self.assertEqual(codex["skills"], "./skills/")
        marketplace = load(REPO / ".claude-plugin" / "marketplace.json")
        self.assertTrue(marketplace.get("description"))
        self.assertEqual([(p["name"], p["source"]) for p in marketplace["plugins"]],
                         [("agent-relay", "./plugins/agent-relay")])

    def test_interface_marker_declares_version_one_and_a_status_command_in_the_plugin(self):
        marker = load(PLUGIN / "interface.json")
        self.assertEqual(marker["interface"], "1.0")
        self.assertEqual(marker["status"][:2], ["python3", "-B"])
        self.assertTrue((PLUGIN / marker["status"][2]).is_file())


class RelayStatusTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-relay-status-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.root = self.home / ".agent-relay" / "runtime"

    def run_status(self):
        # Run exactly as Spec Guard's probe does: the declared argv, from the plugin root.
        argv = load(PLUGIN / "interface.json")["status"]
        done = subprocess.run([sys.executable, *argv[1:]], cwd=PLUGIN, capture_output=True, text=True,
                              env=dict(os.environ, HOME=str(self.home)), timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(set(report), {"ready", "setup"})
        return report

    def make_ready_runtime(self):
        for directory in (self.root, self.root / "mailbox", self.root / "mailbox" / "backups", self.root / "data"):
            directory.mkdir(parents=True, mode=0o700)
            directory.chmod(0o700)
        (self.root / "dist").mkdir()
        (self.root / "dist" / "server.js").write_text("server\n", encoding="utf-8")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}), encoding="utf-8")

    def test_absent_runtime_is_not_ready_with_a_setup_hint_and_nothing_is_created(self):
        report = self.run_status()
        self.assertFalse(report["ready"])
        self.assertIn("/agent-relay:collaboration", report["setup"])
        self.assertFalse((self.home / ".agent-relay").exists())

    def test_ready_runtime_is_ready(self):
        self.make_ready_runtime()
        self.assertEqual(self.run_status(), {"ready": True, "setup": ""})

    def test_invalid_runtime_is_not_ready_and_says_why(self):
        self.make_ready_runtime()
        (self.root / "manifest.json").write_text(json.dumps({"commit": "0" * 40}), encoding="utf-8")
        report = self.run_status()
        self.assertFalse(report["ready"])
        self.assertIn("运行时无效", report["setup"])


if __name__ == "__main__":
    unittest.main()
