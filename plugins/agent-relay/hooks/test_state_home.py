"""AGENT_RELAY_HOME relocates the whole agent-relay state root (test-isolation, D21)."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from native_collaboration_runtime import StateHomeError, default_root, state_home
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


if __name__ == "__main__":
    unittest.main()
