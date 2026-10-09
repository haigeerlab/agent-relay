#!/usr/bin/env python3
"""CI scope (ci-on-demand D135): skip the tests only when every changed path is exempt; full in any doubt."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "ci_scope.py"
ZEROS = "0" * 40


def load_ci_scope():
    import importlib.util
    module_spec = importlib.util.spec_from_file_location("ci_scope", SCRIPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class DecideTest(unittest.TestCase):
    def setUp(self):
        self.ci = load_ci_scope()

    def test_only_exempt_paths_skip(self):
        for event in ("pull_request", "push"):
            scope, reason = self.ci.decide(event, ["CLAUDE.md", "AGENTS.md", "spec/x.md", "tasks/m/todo.md",
                                                   ".agent/state.json", "spec/CAPABILITY-MAP.md"])
            self.assertEqual(scope, "skip", event)
            self.assertIn("exempt", reason)

    def test_one_non_exempt_path_is_full_and_named(self):
        scope, reason = self.ci.decide("pull_request", ["spec/x.md", "plugins/agent-relay/hooks/relay_status.py",
                                                        "README.md"])
        self.assertEqual(scope, "full")
        self.assertIn("plugins/agent-relay/hooks/relay_status.py", reason)

    def test_look_alikes_are_not_exempt(self):
        for path in ("spec.md", "specs/x.md", "tasks.md", ".agent-relay/x", ".agent", "spec", "docs/CLAUDE.md",
                     "plugins/agent-relay/AGENTS.md", "docs/spec/x.md", "claude.md", "README.md", "CHANGELOG.md"):
            scope, reason = self.ci.decide("pull_request", [path])
            self.assertEqual(scope, "full", path)
            self.assertIn(path, reason)

    def test_empty_or_unknown_change_list_is_full(self):
        self.assertEqual(self.ci.decide("pull_request", [])[0], "full")
        self.assertEqual(self.ci.decide("pull_request", None)[0], "full")

    def test_schedule_dispatch_and_other_events_are_full(self):
        for event in ("schedule", "workflow_dispatch", "pull_request_target", "", "merge_group"):
            scope, reason = self.ci.decide(event, ["spec/x.md"])
            self.assertEqual(scope, "full", event)
            self.assertIn(event or "event", reason)


class GitRepoTest(unittest.TestCase):
    """Change lists read from a real repository, through the script's own entry point."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.tmp)], check=False))
        self.git("init", "-q", "-b", "main")
        self.base = self.commit({"plugins/code.py": "x = 1\n", "spec/a.md": "a\n"})

    def git(self, *args):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        return subprocess.run(["git", "-C", str(self.tmp), *args], capture_output=True, text=True, env=env,
                              check=True).stdout.strip()

    def commit(self, files=(), remove=(), rename=None):
        for name, text in dict(files).items():
            path = self.tmp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for name in remove:
            self.git("rm", "-q", name)
        if rename:
            self.git("mv", *rename)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")
        return self.git("rev-parse", "HEAD")

    def run_script(self, event, base, head, output=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CI_", "GITHUB_"))}
        env.update({"CI_EVENT": event, "CI_BASE": base, "CI_HEAD": head})
        if output:
            env["GITHUB_OUTPUT"] = str(output)
        return subprocess.run(["python3", "-B", str(SCRIPT)], cwd=self.tmp, capture_output=True, text=True,
                              env=env)

    def test_pull_request_with_only_exempt_changes_skips_and_writes_the_output(self):
        head = self.commit({"spec/a.md": "a2\n", "tasks/m/todo.md": "t\n"})
        output = self.tmp / "gh-output"
        result = self.run_script("pull_request", self.base, head, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("scope=skip", result.stdout)
        self.assertEqual(output.read_text(), "scope=skip\n")

    def test_pull_request_diff_is_from_the_merge_base(self):
        # The PR branch touches only exempt paths; main moved on with code after the branch point.
        self.git("switch", "-q", "-c", "pr")
        head = self.commit({"tasks/m/todo.md": "t\n"})
        self.git("switch", "-q", "main")
        main = self.commit({"plugins/code.py": "x = 2\n"})
        result = self.run_script("pull_request", main, head)
        self.assertIn("scope=skip", result.stdout, result.stdout + result.stderr)

    def test_code_change_is_full(self):
        head = self.commit({"plugins/code.py": "x = 2\n", "spec/a.md": "a2\n"})
        result = self.run_script("push", self.base, head)
        self.assertIn("scope=full", result.stdout)
        self.assertIn("plugins/code.py", result.stdout)

    def test_moving_code_into_an_exempt_directory_is_full(self):
        head = self.commit(rename=("plugins/code.py", "spec/code.py"))
        result = self.run_script("pull_request", self.base, head)
        self.assertIn("scope=full", result.stdout)
        self.assertIn("plugins/code.py", result.stdout)

    def test_deleting_code_is_full(self):
        head = self.commit(remove=("plugins/code.py",))
        self.assertIn("scope=full", self.run_script("push", self.base, head).stdout)

    def test_new_branch_push_unknown_or_unreachable_base_is_full(self):
        head = self.commit({"spec/a.md": "a2\n"})
        for base in (ZEROS, "", "1234567890abcdef1234567890abcdef12345678"):
            result = self.run_script("push", base, head)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("scope=full", result.stdout, base)

    def test_schedule_is_full_without_a_diff(self):
        output = self.tmp / "gh-output"
        result = self.run_script("schedule", "", "", output)
        self.assertIn("scope=full", result.stdout)
        self.assertEqual(output.read_text(), "scope=full\n")


if __name__ == "__main__":
    unittest.main()
