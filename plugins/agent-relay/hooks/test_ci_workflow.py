"""The CI workflow runs the local validation on macOS with least privilege (ci-macos D80, D80a, D82), skips it when
only exempt paths changed and runs it weekly (ci-on-demand D135-D139).

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
        # C8: no permission at the top; each job asks for what it needs, and no job may write.
        self.assertRegex(self.text, r"(?m)^permissions: \{\}\n")
        self.assertEqual(self.text.count("permissions:\n      contents: read\n"), 2)
        self.assertNotRegex(self.text, r": write\b")
        self.assertNotIn("secrets.", self.text)
        self.assertEqual(self.text.count("uses: actions/checkout@"), self.text.count("persist-credentials: false"))
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
        self.assertIn('ok    bridge: npm run check +[0-9]+$', self.text, "the bridge check must report a test count")

    def test_weekly_full_run(self):
        self.assertRegex(self.text, r"(?m)^  schedule:\n    - cron: '0 3 \* \* 1'$")

    def steps(self):
        """The validate job's steps, each as its own text block, in order."""
        body = self.text.split("\n    steps:\n", 1)[1].split("\n\n  # ", 1)[0]
        return [block for block in re.split(r"\n(?=      - )", body) if block.startswith("      - ")]

    def test_scope_is_decided_from_environment_with_full_history(self):
        steps = self.steps()
        self.assertIn("uses: actions/checkout@", steps[0])
        self.assertIn("fetch-depth: 0", steps[0], "the scope needs the PR base and the push's before")
        scope = steps[2]
        self.assertIn("id: scope", scope)
        self.assertRegex(scope, r"(?m)^        run: python3 -B scripts/ci_scope\.py$")
        self.assertIn("CI_EVENT: ${{ github.event_name }}", scope)
        self.assertIn("CI_BASE: ${{ github.event.pull_request.base.sha || github.event.before }}", scope)
        self.assertIn("CI_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}", scope)
        self.assertNotIn("if:", scope, "the scope step itself always runs")

    def test_every_later_step_runs_unless_the_scope_is_skip(self):
        later = self.steps()[3:]
        self.assertGreaterEqual(len(later), 6)
        for step in later:
            # `!= 'skip'`, not `== 'full'`: a missing output must run the tests, not pass without them.
            self.assertRegex(step, r"(?m)^        if: steps\.scope\.outputs\.scope != 'skip'( && .+)?$", step)
        joined = "\n".join(later)
        for needed in ("npm ci", "toolchain", "bash scripts/validate.sh", "git diff --exit-code"):
            self.assertIn(needed, joined, f"{needed} must stay after the scope step")

    def test_local_path_check_runs_before_the_scope_and_is_never_skipped(self):
        # S107: a change to exempt paths only (spec/, tasks/) skips the tests, but not this check.
        check = self.steps()[1]
        self.assertRegex(check, r"(?m)^        run: python3 -B scripts/check_local_paths\.py$")
        self.assertNotIn("if:", check)

    def test_plugin_manifests_and_frontmatter_are_checked(self):
        # C7: the CLI is pinned to an exact version and fails on warnings (--strict), and the frontmatter check fails where the CLI only warns.
        self.assertRegex(self.text, r"npm install --global @anthropic-ai/claude-code@\d+\.\d+\.\d+\n")
        self.assertRegex(self.text, r"pip install pyyaml==\d+\.\d+\.\d+\n")
        self.assertIn("claude plugin validate --strict plugins/agent-relay\n", self.text)
        self.assertIn("claude plugin validate --strict .\n", self.text)
        self.assertIn("run: python3 -B scripts/check_frontmatter.py\n", self.text)

    def test_ci_required_gathers_every_other_job(self):
        # C1: one required check that fails unless every other job succeeded, and no path filter on the workflow.
        jobs = re.findall(r"(?m)^  ([a-z][a-z0-9-]*):$", self.text.split("\njobs:\n", 1)[1])
        self.assertEqual(jobs[-1], "ci-required")
        gate = self.text.split("\n  ci-required:\n", 1)[1]
        self.assertIn("name: CI required\n", gate)
        self.assertIn("if: always()\n", gate)
        self.assertIn(f"needs: [{', '.join(jobs[:-1])}]\n", gate)
        self.assertIn("join(needs.*.result, ' ')", gate)
        self.assertIn('[ "$result" = success ] || exit 1', gate)
        self.assertNotRegex(self.text, r"(?m)^\s+paths(-ignore)?:")


if __name__ == "__main__":
    unittest.main()
