"""relay_status.py (interface.json `status`) tells Spec Guard how to get the runtime ready (D4); an interrupted swap
needs `recover`, not an install that would be refused (upgrade-recovery, found in the round-2 review of #34)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOKS = Path(__file__).resolve().parent


class RelayStatusTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-relay-status-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve() / "relay"
        self.home.mkdir(mode=0o700)

    def run_status(self):
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.home.parent),
                       "AGENT_RELAY_HOME": str(self.home)}
        done = subprocess.run([sys.executable, "-B", str(HOOKS / "relay_status.py")], env=environment,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        return json.loads(done.stdout)

    def test_an_interrupted_swap_points_to_recover(self):
        (self.home / "runtime-swap.json").write_text(json.dumps({
            "kind": "upgrade", "step": "promoting", "runtime": str(self.home / "runtime"),
            "incoming": str(self.home / ".runtime-upgrade-x"), "outgoing": None, "park": str(self.home / "park")}))
        result = self.run_status()
        self.assertFalse(result["ready"])
        self.assertIn("recover --confirm", result["setup"])
        self.assertIn("中途停止", result["setup"])
        self.assertNotIn("/agent-relay:collaboration", result["setup"], "an install would be refused")

    def test_an_unreadable_journal_still_answers(self):
        (self.home / "runtime-swap.json").write_text("not json")
        result = self.run_status()
        self.assertFalse(result["ready"])
        self.assertIn("runtime-swap.json", result["setup"])
        self.assertNotIn("/agent-relay:collaboration", result["setup"], "an install would be refused too")

    def test_a_missing_runtime_still_points_to_setup(self):
        result = self.run_status()
        self.assertFalse(result["ready"])
        self.assertIn("/agent-relay:collaboration", result["setup"])


if __name__ == "__main__":
    unittest.main()
