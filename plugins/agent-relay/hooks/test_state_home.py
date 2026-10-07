"""AGENT_RELAY_HOME relocates the whole agent-relay state root (test-isolation, D21)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from native_collaboration_runtime import BRIDGE_COMMIT, StateHomeError, default_root, state_home
from session_delegation import AuthorizationRequest, DelegationStore
from session_delegation_control import default_state_root
import state_migration


class StateHomeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ar-state-home-")
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name).resolve()

    def environ(self, **values):
        patcher = mock.patch.dict(os.environ, values)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unset_and_empty_fall_back_to_the_home_directory(self):
        for value in (None, ""):
            with self.subTest(value=value):
                with mock.patch.dict(os.environ, {"HOME": str(self.tmp)}):
                    os.environ.pop("AGENT_RELAY_HOME", None)
                    if value is not None:
                        os.environ["AGENT_RELAY_HOME"] = value
                    self.assertEqual(state_home(), self.tmp / ".agent-relay")

    def test_absolute_value_is_the_state_root(self):
        self.environ(AGENT_RELAY_HOME=str(self.tmp / "relay"))
        self.assertEqual(state_home(), self.tmp / "relay")

    def test_relative_value_is_refused_naming_the_variable(self):
        self.environ(AGENT_RELAY_HOME="relative/relay")
        with self.assertRaisesRegex(StateHomeError, "AGENT_RELAY_HOME"):
            state_home()

    def test_every_default_path_derives_from_the_state_root(self):
        self.environ(AGENT_RELAY_HOME=str(self.tmp / "relay"))
        self.assertEqual(default_root(), self.tmp / "relay" / "runtime")
        self.assertEqual(default_state_root(), self.tmp / "relay" / "delegation")
        self.assertEqual(state_migration.default_target(), self.tmp / "relay")

    def test_migration_target_is_explicit_in_the_library(self):
        # The library keeps `<home>/.agent-relay` unless told otherwise, so a test that passes
        # a temporary home can never reach the real state root.
        self.environ(AGENT_RELAY_HOME=str(self.tmp / "relay"))
        home = self.tmp / "old-home"
        self.assertEqual(state_migration.inspect(home).target_root, home / ".agent-relay")
        self.assertEqual(state_migration.inspect(home, target=self.tmp / "explicit").target_root,
                         self.tmp / "explicit")

    def test_migration_cli_refuses_a_relative_state_root(self):
        self.environ(AGENT_RELAY_HOME="relative/relay", HOME=str(self.tmp))
        with self.assertRaises(SystemExit) as caught, \
                mock.patch("sys.stderr") as stderr:
            state_migration.main(["detect"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("AGENT_RELAY_HOME", "".join(
            call.args[0] for call in stderr.write.call_args_list))



HOOKS = Path(__file__).resolve().parent
REPO = HOOKS.parents[2]


class EntryPointSweepTests(unittest.TestCase):
    """Every entry point follows AGENT_RELAY_HOME; none still builds ~/.agent-relay itself."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ar-sweep-")
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name).resolve()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.relay = self.tmp / "relay"
        self.runtime = self.relay / "runtime"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("claude", 'echo "9.9.9 (Claude Code)"'),
                           ("codex", 'echo "codex-cli 9.0"')):
            path = self.bin / name
            path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
            path.chmod(0o755)
        self.node = self.bin / "node"
        self.node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.node.chmod(0o755)

    def plant_runtime(self):
        self.relay.mkdir(mode=0o700)
        self.runtime.mkdir(mode=0o700)
        for sub in ("mailbox", "mailbox/backups", "data"):
            (self.runtime / sub).mkdir(mode=0o700)
        (self.runtime / "dist").mkdir()
        (self.runtime / "dist" / "server.js").write_text("server\n")
        (self.runtime / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))

    def run_entry(self, *command, value=None):
        env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(self.home),
               "AGENT_RELAY_HOME": str(self.relay) if value is None else value,
               "CLAUDE_CONFIG_DIR": str(self.tmp / "claude"), "CODEX_HOME": str(self.tmp / "codex")}
        return subprocess.run(list(command), capture_output=True, text=True, env=env,
                              cwd=self.tmp, timeout=60)

    def python(self, script, *args, value=None):
        return self.run_entry(sys.executable, "-B", str(HOOKS / script), *args, value=value)

    def test_every_entry_point_reads_the_relocated_root(self):
        self.plant_runtime()
        store = DelegationStore(self.relay / "delegation", now=lambda: 1_800_000_000)
        envelope = store.authorize(AuthorizationRequest(
            authority="direct-user", horizon="task", origin_host="claude",
            origin_session="origin", project_root=self.tmp, repo_identity="git:x/y",
            baseline="a" * 40, dirty=False, target_hosts=("codex",),
            permission_intent="safe-review", host_permission=None, max_sessions=1,
            expires_at=1_800_000_600, depth=0, idempotency_key="sweep-request-1",
            summary="sweep"))
        store.claim_launch(envelope.envelope_id, "sweep-launch-1", "codex", self.tmp,
                           "a" * 40, "safe-review", friendly_name="sweep-entry")

        runtime = self.python("native_collaboration_runtime.py", "status")
        self.assertEqual(json.loads(runtime.stdout)["state"], "ready", runtime.stderr)
        probe = self.python("relay_status.py")
        self.assertTrue(json.loads(probe.stdout)["ready"], probe.stderr)
        retire = self.python("native_collaboration_retire.py", "--name", "nobody",
                             "--node", str(self.node), "--confirm-retire")
        self.assertNotIn("not ready", retire.stdout, retire.stderr)
        listing = self.python("session_delegation_control.py", "list")
        self.assertIn("sweep-entry", listing.stdout, listing.stderr)
        detect = self.python("state_migration.py", "detect")
        self.assertEqual(json.loads(detect.stdout)["target_runtime"], "ready", detect.stderr)
        preflight = self.run_entry("/bin/bash", str(REPO / "scripts" / "acceptance" / "preflight.sh"))
        self.assertIn(f"runtime root          {self.runtime} (present)", preflight.stdout,
                      preflight.stderr)
        cleanup = self.run_entry("/bin/bash", str(REPO / "scripts" / "acceptance" / "cleanup.sh"),
                                 "sweep")
        self.assertIn(str(self.runtime / "mailbox" / "bridge.sqlite"), cleanup.stdout,
                      cleanup.stderr)
        self.assertEqual(sorted(path.name for path in self.home.iterdir()), [])

    def test_host_entries_get_the_resolved_absolute_paths(self):
        self.plant_runtime()
        database = str(self.runtime / "mailbox" / "bridge.sqlite")
        data_home = str(self.runtime / "data")
        codex_config = self.tmp / "codex.toml"
        installed = self.python("native_collaboration_adapters.py", "install-codex",
                                "--node", str(self.node), "--codex-config", str(codex_config))
        self.assertEqual(installed.returncode, 0, installed.stderr)
        text = codex_config.read_text(encoding="utf-8")
        self.assertIn(f"BRIDGE_DB_PATH = {json.dumps(database)}", text)
        self.assertIn(f"XDG_DATA_HOME = {json.dumps(data_home)}", text)
        claude = self.python("native_collaboration_adapters.py", "claude", "--node", str(self.node))
        server = json.loads(claude.stdout)["mcpServers"]["agent-relay"]
        self.assertEqual(server["env"], {"BRIDGE_DB_PATH": database, "XDG_DATA_HOME": data_home})

    def test_a_relative_root_is_refused_by_every_entry_point_without_a_traceback(self):
        for script, args in (("native_collaboration_runtime.py", ("status",)),
                             ("native_collaboration_adapters.py", ("codex",)),
                             ("native_collaboration_retire.py", ("--name", "x", "--confirm-retire")),
                             ("session_delegation_control.py", ("list",)),
                             ("state_migration.py", ("detect",))):
            with self.subTest(script=script):
                done = self.python(script, *args, value="relative/relay")
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("AGENT_RELAY_HOME", done.stderr)
                self.assertNotIn("Traceback", done.stderr)
        probe = self.python("relay_status.py", value="relative/relay")
        self.assertIn("AGENT_RELAY_HOME", probe.stdout)
        cleanup = self.run_entry("/bin/bash", str(REPO / "scripts" / "acceptance" / "cleanup.sh"),
                                 "sweep", value="relative/relay")
        self.assertEqual(cleanup.returncode, 2)
        self.assertIn("AGENT_RELAY_HOME", cleanup.stderr)
        preflight = self.run_entry("/bin/bash", str(REPO / "scripts" / "acceptance" / "preflight.sh"),
                                   value="relative/relay")
        self.assertIn("runtime root          error: AGENT_RELAY_HOME", preflight.stdout)

    def test_no_other_module_builds_the_state_root_from_the_home_directory(self):
        allowed = {"native_collaboration_runtime.py", "state_migration.py"}
        sources = [path for path in sorted(HOOKS.glob("*.py")) if not path.name.startswith("test_")]
        sources += sorted((REPO / "scripts" / "acceptance").glob("*.sh"))
        offenders = [path.name for path in sources if path.name not in allowed
                     and re.search(r"[\"']\.agent-relay[\"'/]", path.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])



class SealedRunTests(unittest.TestCase):
    """Under scripts/validate.sh no test can reach the user's state or host config (D22)."""

    def test_the_validate_run_points_every_root_into_its_seal(self):
        seal = os.environ.get("AGENT_RELAY_TEST_SEAL")
        if not seal:
            self.skipTest("only meaningful inside scripts/validate.sh")
        seal = Path(seal).resolve()
        for path in (Path.home(), state_home(), default_root(),
                     Path(os.environ["CLAUDE_CONFIG_DIR"]), Path(os.environ["CODEX_HOME"])):
            self.assertTrue(path.resolve().is_relative_to(seal), path)


if __name__ == "__main__":
    unittest.main()
