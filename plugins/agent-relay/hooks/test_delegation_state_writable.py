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

import sqlite3
import time

from session_delegation import AuthorizationRequest, DelegationStore

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

    # delegation-status-read-only D189 -------------------------------------------------------------------------------
    def filled(self) -> tuple[Path, str]:
        """A store with one created Claude delegation named 复审, made outside the sandbox."""
        state = self.root / "delegation"
        store = DelegationStore(state)
        envelope = store.authorize(AuthorizationRequest(
            authority="direct-user", horizon="task", origin_host="codex", origin_session="origin",
            project_root=self.project, repo_identity="git:example/project", baseline="a" * 40, dirty=False,
            target_hosts=("claude",), permission_intent="safe-review", host_permission=None, max_sessions=1,
            expires_at=int(time.time()) + 3600, depth=0, idempotency_key="read-only-12345678", summary="Review"))
        claim = store.claim_launch(envelope.envelope_id, "read-only-launch", "claude", self.project, "a" * 40,
                                   "safe-review", friendly_name="复审")
        store.bind_host(claim.delegation_id, "ce5b9501", "ce5b9501-0817-479d-886e-772bafbbee6f", "2.1.295",
                        "dontAsk/safe-review")
        return state, claim.delegation_id

    def run_command(self, state: Path, *arguments: str, stdin: str = "") -> subprocess.CompletedProcess:
        profile = '(version 1)(allow default)(deny file-write* (subpath "%s"))' % state
        command = [SANDBOX, "-p", profile, "python3", "-B", str(HOOKS / "session_delegation_control.py"),
                   "--state-root", str(state), "--node", NODE, *arguments]
        env = {**os.environ, "CODEX_THREAD_ID": "thread-read-only", "HOME": str(self.root)}
        return subprocess.run(command, input=stdin, capture_output=True, text=True, env=env, timeout=60)

    @staticmethod
    def snapshot(state: Path) -> dict:
        return {path.name: (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else b"")
                for path in [state, *state.iterdir()]}

    def test_looking_at_delegations_works_read_only_and_changes_no_file(self):
        state, _delegation = self.filled()
        before = self.snapshot(state)
        listed = self.run_command(state, "list")
        self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
        self.assertEqual([(item["name"], item["state"], item["readOnly"]) for item in json.loads(listed.stdout)],
                         [("复审", "created", True)])
        for arguments in (("resolve", "--name", "复审"), ("prune",)):
            done = self.run_command(state, *arguments)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIs(json.loads(done.stdout)["readOnly"], True, arguments)
        status = self.run_command(state, "status", "--name", "复审")
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual((payload["name"], payload["state"], payload["readOnly"]), ("复审", "created", True))
        self.assertIn("may be behind", payload["detail"])
        # The coordinator's note on #85: the failed writable attempt itself must leave nothing behind either.
        self.assertEqual(self.snapshot(state), before)

    def test_commands_that_must_write_still_say_not_writable(self):
        state, _delegation = self.filled()
        before = self.snapshot(state)
        for arguments, stdin in ((("cancel", "--name", "复审"), ""), (("continue", "--name", "复审"), "again"),
                                 (("prune", "--confirm", "deadbeef"), "")):
            self.assert_clear(self.run_command(state, *arguments, stdin=stdin))
        self.assertEqual(self.snapshot(state), before)

    def test_a_store_that_needs_migration_or_cannot_be_read_names_the_reason(self):
        state, _delegation = self.filled()
        with sqlite3.connect(state / "delegation.sqlite") as connection:
            connection.execute("PRAGMA user_version = 2")
        done = self.run_command(state, "list")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        payload = json.loads(done.stdout)
        self.assertEqual(payload["reason"], "delegation-store-needs-migration")
        self.assertIn("outside the sandbox", payload["detail"])
        self.assertFalse((state / "delegation.schema2.sqlite").exists())

        with sqlite3.connect(state / "delegation.sqlite") as connection:
            connection.execute("PRAGMA user_version = 3")
        writer = sqlite3.connect(state / "delegation.sqlite", isolation_level=None)
        # Apple's SQLite build does not spill an open transaction to the file unless told to; without the spill the
        # copy below is an intact database with a cold journal, which is readable (and correct) read-only.
        writer.execute("PRAGMA cache_spill = 1")
        writer.execute("PRAGMA cache_size = 1")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("CREATE TABLE junk (a, b)")
        writer.executemany("INSERT INTO junk VALUES (?, ?)", [(index, "x" * 2000) for index in range(300)])
        crashed = self.root / "crashed"
        crashed.mkdir(mode=0o700)
        for name in ("delegation.sqlite", "delegation.sqlite-journal"):
            (crashed / name).write_bytes((state / name).read_bytes())
            (crashed / name).chmod(0o600)
        writer.execute("ROLLBACK")
        writer.close()
        unreadable = self.run_command(crashed, "status", "--name", "复审")
        self.assertEqual(unreadable.returncode, 1, unreadable.stdout + unreadable.stderr)
        self.assertEqual(json.loads(unreadable.stdout)["reason"], "state-not-readable")
        self.assertNotIn("Traceback", unreadable.stdout + unreadable.stderr)

    def test_a_writable_store_answers_as_before_without_read_only(self):
        state, _delegation = self.filled()
        command = ["python3", "-B", str(HOOKS / "session_delegation_control.py"), "--state-root", str(state),
                   "--node", NODE, "list"]
        done = subprocess.run(command, capture_output=True, text=True, timeout=60,
                              env={**os.environ, "HOME": str(self.root)})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("readOnly", done.stdout)

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
