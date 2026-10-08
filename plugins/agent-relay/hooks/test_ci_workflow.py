"""The CI workflow runs the local validation on macOS with least privilege (ci-macos D80, D80a, D82).

Plain text checks (no YAML library): the file is small and its shape is fixed by the spec.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


class CiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(WORKFLOW.is_file(), f"{WORKFLOW} is missing")
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_triggers_and_no_privileged_event(self):
        self.assertRegex(self.text, r"(?m)^  pull_request:")
        self.assertRegex(self.text, r"(?m)^  push:\n    branches: \[main\]")
        self.assertRegex(self.text, r"(?m)^  workflow_dispatch:")
        self.assertNotIn("pull_request_target", self.text)

    def test_least_privilege(self):
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\n")
        self.assertNotIn("secrets.", self.text)
        self.assertIn("persist-credentials: false", self.text)
        self.assertNotIn("self-hosted", self.text)

    def test_every_action_is_pinned_to_a_full_sha(self):
        uses = re.findall(r"uses: (\S+)", self.text)
        self.assertGreaterEqual(len(uses), 3)
        for use in uses:
            self.assertRegex(use, r"^actions/(checkout|setup-python|setup-node)@[0-9a-f]{40}$", use)

    def test_macos_15_full_matrix(self):
        self.assertIn("runs-on: macos-15", self.text)
        self.assertRegex(self.text, r"python: \['3\.9', '3\.14'\]")
        self.assertRegex(self.text, r"node: \['22', '24'\]")
        self.assertIn("timeout-minutes: 20", self.text)

    def test_python_39_is_apples_and_versions_are_asserted(self):
        self.assertIn("/usr/bin/python3", self.text)
        self.assertIn("matrix.python == '3.9'", self.text)
        self.assertIn("python-version: '3.14'", self.text)
        self.assertIn("node-version: ${{ matrix.node }}", self.text)
        self.assertIn("sys.version_info", self.text, "the job fails on the wrong Python")
        self.assertIn("process.versions.node", self.text, "the job fails on the wrong Node")

    def test_toolchain_is_printed_and_the_bridge_check_cannot_be_skipped(self):
        self.assertIn("npm ci", self.text)
        self.assertIn("toolchain", self.text)
        self.assertIn("bash scripts/validate.sh", self.text)
        self.assertIn("ok    bridge: npm run check", self.text)


if __name__ == "__main__":
    unittest.main()
