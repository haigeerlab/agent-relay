#!/usr/bin/env python3
"""Tests for scripts/quick_scope.py and validate.sh's public argument contract."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "quick_scope.py"
VALIDATE = REPO / "scripts" / "validate.sh"


def load_scope():
    spec = importlib.util.spec_from_file_location("quick_scope", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuickScopeTest(unittest.TestCase):
    def setUp(self):
        self.scope = load_scope()
        self.tmp = tempfile.TemporaryDirectory()
        self.hooks = Path(self.tmp.name)
        (self.hooks / "test_alpha.py").write_text("import utility\n", encoding="utf-8")
        (self.hooks / "test_beta.py").write_text("utility.call()\n", encoding="utf-8")
        (self.hooks / "test_other.py").write_text("nothing_here = True\n", encoding="utf-8")
        (self.hooks / "utility.py").write_text("pass\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def decide(self, paths):
        return self.scope.decide(paths, self.hooks)

    def test_changed_test_runs_only_that_test(self):
        self.assertEqual(self.decide(["plugins/agent-relay/hooks/test_alpha.py"]),
                         ("quick", "from 1 changed paths", ["test_alpha.py"], False))

    def test_changed_module_runs_tests_that_mention_it(self):
        mode, reason, tests, bridge = self.decide(["plugins/agent-relay/hooks/utility.py"])
        self.assertEqual((mode, reason, bridge), ("quick", "from 1 changed paths", False))
        self.assertEqual(tests, ["test_alpha.py", "test_beta.py"])

    def test_transitive_module_dependents_are_selected(self):
        (self.hooks / "a.py").write_text("pass\n", encoding="utf-8")
        (self.hooks / "b.py").write_text("import a\n", encoding="utf-8")
        (self.hooks / "test_b.py").write_text("import b\n", encoding="utf-8")
        self.assertEqual(
            self.decide(["plugins/agent-relay/hooks/a.py"])[2], ["test_b.py"])

    def test_transitive_test_dependents_are_selected(self):
        (self.hooks / "test_x.py").write_text("pass\n", encoding="utf-8")
        (self.hooks / "test_y.py").write_text("import test_x\n", encoding="utf-8")
        self.assertEqual(
            self.decide(["plugins/agent-relay/hooks/test_x.py"])[2],
            ["test_x.py", "test_y.py"])

    def test_closure_terminates_on_import_cycle(self):
        (self.hooks / "a.py").write_text("import b\n", encoding="utf-8")
        (self.hooks / "b.py").write_text("import a\n", encoding="utf-8")
        (self.hooks / "test_b.py").write_text("import b\n", encoding="utf-8")
        self.assertEqual(
            self.decide(["plugins/agent-relay/hooks/a.py"])[2], ["test_b.py"])

    def test_module_with_no_test_mention_falls_back(self):
        (self.hooks / "unused.py").write_text("pass\n", encoding="utf-8")
        self.assertEqual(self.decide(["plugins/agent-relay/hooks/unused.py"])[0], "full")

    def test_bridge_runs_bridge_vendoring_and_runtime_dependents(self):
        (self.hooks / "test_bridge_vendoring.py").write_text("pass\n", encoding="utf-8")
        (self.hooks / "native_collaboration_runtime.py").write_text("pass\n", encoding="utf-8")
        (self.hooks / "test_runtime.py").write_text(
            "import native_collaboration_runtime\n", encoding="utf-8")
        mode, reason, tests, bridge = self.decide(
            ["plugins/agent-relay/bridge/src/index.ts"])
        self.assertEqual((mode, reason, bridge), ("quick", "from 1 changed paths", True))
        self.assertEqual(tests, ["test_bridge_vendoring.py", "test_runtime.py"])

    def test_unmapped_paths_fall_back(self):
        for path in ("scripts/x.sh", ".github/workflows/ci.yml", "CLAUDE" + ".md"):
            with self.subTest(path=path):
                self.assertEqual(self.decide([path])[0], "full")

    def test_mixed_paths_fall_back(self):
        self.assertEqual(self.decide(["plugins/agent-relay/bridge/a.ts", "docs/x.md"])[0], "full")

    def test_no_paths_falls_back(self):
        self.assertEqual(self.decide([])[0], "full")

    def test_deleted_test_file_is_ignored(self):
        self.assertEqual(self.decide(["plugins/agent-relay/hooks/test_deleted.py"])[0], "full")


class RealHooksScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope = load_scope()
        cls.hooks = REPO / "plugins" / "agent-relay" / "hooks"

    def test_node_select_reaches_runtime_upgrade(self):
        tests = self.scope.decide(
            ["plugins/agent-relay/hooks/node_select.py"], self.hooks)[2]
        self.assertIn("test_runtime_upgrade.py", tests)

    def test_runtime_upgrade_reaches_its_dependents(self):
        tests = self.scope.decide(
            ["plugins/agent-relay/hooks/test_runtime_upgrade.py"], self.hooks)[2]
        self.assertIn("test_runtime_recovery.py", tests)

    def test_bridge_selects_vendoring_test(self):
        tests = self.scope.decide(
            ["plugins/agent-relay/bridge/src/addressing.ts"], self.hooks)[2]
        self.assertIn("test_bridge_vendoring.py", tests)


class ValidateContractTest(unittest.TestCase):
    def test_unknown_argument_is_usage_error(self):
        result = subprocess.run(["bash", str(VALIDATE), "--unknown"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)

    def test_full_mode_keeps_bridge_ci_format(self):
        text = VALIDATE.read_text(encoding="utf-8")
        self.assertIn('"bridge: npm run check"', text)
        self.assertIn('printf \'  ok    %-52s %s\\n\'', text)

    def test_validate_is_bash_32_compatible(self):
        result = subprocess.run(["/bin/bash", "-n", str(VALIDATE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = VALIDATE.read_text(encoding="utf-8")
        self.assertNotIn("mapfile", text)
        self.assertNotIn("readarray", text)

    def test_full_fallbacks_restore_bridge(self):
        text = VALIDATE.read_text(encoding="utf-8")
        start = text.index("full_fallback() {")
        end = text.index("}\n", start)
        self.assertIn("BRIDGE_NEEDED=1", text[start:end])
        for reason in (
            'full_fallback "quick fell back: origin/main is unavailable"',
            'full_fallback "quick fell back: merge-base is unavailable"',
            'full_fallback "quick fell back: git diff failed"',
            'full_fallback "$REASON"',
        ):
            self.assertIn(reason, text)

    def test_ran_nothing_failure_is_quick_only(self):
        text = VALIDATE.read_text(encoding="utf-8")
        self.assertIn('if [ "$QUICK" -eq 1 ] && [ "$FILES" -eq 0 ] && [ "$BRIDGE_RAN" -eq 0 ]; then', text)
        self.assertIn('echo "validate: quick mode ran nothing"', text)


if __name__ == "__main__":
    unittest.main()
