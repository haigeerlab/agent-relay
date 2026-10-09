#!/usr/bin/env python3
"""delegation-cross-host D160: a state the controller cannot write gets a clear answer, never a traceback.

Reproduced the way Codex meets it on macOS: the command runs under a seatbelt profile that denies writes below the
state location (directory modes stay as the store requires), like Codex's default sandbox outside the workspace.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from session_delegation import DelegationStore

HOOKS = Path(__file__).resolve().parent
SANDBOX = shutil.which("sandbox-exec")
NODE = shutil.which("node")


@unittest.skipUnless(SANDBOX and NODE, "needs macOS sandbox-exec and a node")
class StateNotWritableTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ar-state-ro-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()

    def run_create(self, state: Path, deny: Path) -> subprocess.CompletedProcess:
        profile = '(version 1)(allow default)(deny file-write* (subpath "%s"))' % deny
        command = [SANDBOX, "-p", profile, "python3", "-B", str(HOOKS / "session_delegation_control.py"),
                   "--state-root", str(state), "--node", NODE, "create",
                   "--origin-host", "codex", "--target-host", "claude", "--project", str(self.project),
                   "--repo-identity", "git:example/project", "--baseline", "a" * 40,
                   "--expires-at", "2030-01-01T00:00:00Z", "--idempotency-key", "read-only-12345678",
                   "--launch-key", "read-only-launch", "--name", "只读", "--summary", "Review"]
        env = {**os.environ, "CODEX_THREAD_ID": "thread-read-only", "HOME": str(self.root)}
        return subprocess.run(command, input="Review this", capture_output=True, text=True, env=env, timeout=60)

    def assert_clear(self, done: subprocess.CompletedProcess):
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertNotIn("Traceback", done.stdout + done.stderr)
        payload = json.loads(done.stdout)
        self.assertEqual(payload["state"], "error")
        self.assertEqual(payload["reason"], "state-not-writable")
        self.assertIn("sandbox", payload["detail"])

    def test_an_existing_state_the_sandbox_will_not_let_us_write(self):
        state = self.root / "delegation"
        DelegationStore(state)  # created by an earlier run outside the sandbox
        self.assert_clear(self.run_create(state, deny=state))

    def test_a_state_directory_the_sandbox_will_not_let_us_create(self):
        parent = self.root / "agent-relay"
        parent.mkdir(mode=0o700)
        self.assert_clear(self.run_create(parent / "delegation", deny=parent))


if __name__ == "__main__":
    unittest.main()
