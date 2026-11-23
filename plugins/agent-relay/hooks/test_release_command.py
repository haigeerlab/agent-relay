#!/usr/bin/env python3
"""Release commands: isolated repositories, fake host tools and the D278/D286 contract."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "release.py"
REAL_GIT = shutil.which("git")


def load_release():
    module_spec = importlib.util.spec_from_file_location("release_command", SCRIPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


FAKE_TOOL = '''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

tool = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["RELEASE_CALLS"], "a", encoding="utf-8") as log:
    log.write(json.dumps([tool, *args]) + "\\n")
answers = json.loads((Path(os.environ["RELEASE_ANSWERS"]) / (tool + ".json")).read_text())
answer = answers.get("default", {})
for entry in answers.get("responses", []):
    if entry["args"] == args:
        answer = entry
        break
sys.stdout.write(answer.get("stdout", ""))
sys.stderr.write(answer.get("stderr", ""))
sys.exit(answer.get("returncode", 0))
'''


LOGGING_GIT = '''#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["RELEASE_CALLS"], "a", encoding="utf-8") as log:
    log.write(json.dumps(["git", *sys.argv[1:]]) + "\\n")
os.execv(os.environ["RELEASE_REAL_GIT"], ["git", *sys.argv[1:]])
'''


class Fixture:
    """A real local Git pair and programmable tools; no real host or network is used."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ar-release-test-")
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "remote.git"
        self.bin = self.root / "bin"
        self.answers = self.root / "answers"
        self.calls_log = self.root / "calls.log"
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.claude = self.root / "claude"
        self.codex = self.root / "codex"
        for directory in (self.repo, self.bin, self.answers, self.home, self.state, self.claude, self.codex):
            directory.mkdir()
        self.calls_log.write_text("", encoding="utf-8")
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update({
            "HOME": str(self.home), "AGENT_RELAY_HOME": str(self.state),
            "CLAUDE_CONFIG_DIR": str(self.claude), "CODEX_HOME": str(self.codex),
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "RELEASE_CALLS": str(self.calls_log), "RELEASE_ANSWERS": str(self.answers),
            "RELEASE_REAL_GIT": REAL_GIT,
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "Release Test", "GIT_COMMITTER_NAME": "Release Test",
            "GIT_AUTHOR_EMAIL": "release@example.invalid", "GIT_COMMITTER_EMAIL": "release@example.invalid",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        for tool in ("gh", "claude", "codex", "ps", "node"):
            executable = self.bin / tool
            executable.write_text(FAKE_TOOL, encoding="utf-8")
            executable.chmod(0o755)
            self.answer(tool)
        executable = self.bin / "git"
        executable.write_text(LOGGING_GIT, encoding="utf-8")
        executable.chmod(0o755)
        self.git("init", "-q", "--bare", "--template=", str(self.remote))
        self.git("init", "-q", "-b", "main", "--template=")
        self.git("remote", "add", "origin", str(self.remote))
        self.version = "1.2.3"
        plugin = "plugins/agent-relay/"
        files = {
            ".claude-plugin/marketplace.json": json.dumps({"name": "agent-relay-marketplace", "plugins": [
                {"name": "agent-relay", "source": "./plugins/agent-relay"}]}),
            plugin + ".claude-plugin/plugin.json": json.dumps({"name": "agent-relay", "version": self.version}),
            plugin + ".codex-plugin/plugin.json": json.dumps({"name": "agent-relay", "version": self.version}),
            plugin + "interface.json": json.dumps({"interface": "2.11"}),
            plugin + "bridge/package.json": json.dumps({"name": "agent-relay-bridge", "version": self.version}),
            plugin + "bridge/src/x.ts": "export const x = 1;\n",
            plugin + "bridge/test/x.test.ts": "// A test-only bridge file.\n",
            "README.md": "> 状态：1.2.3（接口 2.11）\n安装：--ref v1.2.3\n",
            "README.en.md": "> Status: 1.2.3 (interface 2.11)\nInstall: --ref v1.2.3\n",
            "CHANGELOG.md": "# Changelog\n\n## [1.2.3]\n\nRelease test notes.\n\n## [1.2.2]\n\nOlder notes.\n",
        }
        self.head = self.commit(files)
        self.git("push", "-q", "-u", "origin", "main")

    def close(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run([REAL_GIT, "-c", "core.hooksPath=" + os.devnull, "-C", str(self.repo), *args],
                              env=self.env, capture_output=True, text=True, check=True, timeout=30).stdout.strip()

    def commit(self, files):
        for name, contents in files.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "test fixture")
        return self.git("rev-parse", "HEAD")

    def answer(self, tool, args=None, stdout="", stderr="", returncode=0):
        """Set a default response or one exact argv response for a fake tool."""
        path = self.answers / (tool + ".json")
        answers = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        response = {"stdout": stdout, "stderr": stderr, "returncode": returncode}
        if args is None:
            answers["default"] = response
        else:
            responses = [entry for entry in answers.get("responses", []) if entry["args"] != list(args)]
            answers["responses"] = [*responses, {"args": list(args), **response}]
        path.write_text(json.dumps(answers), encoding="utf-8")

    def calls(self):
        return [json.loads(line) for line in self.calls_log.read_text(encoding="utf-8").splitlines()]

    def run_release(self, *args):
        arguments = list(args)
        if arguments and arguments[0] in ("check", "prepare", "publish", "install", "upgrade", "smoke", "evidence"):
            if "--repo" not in arguments:
                arguments[1:1] = ["--repo", str(self.repo)]
        done = subprocess.run([sys.executable, "-B", str(SCRIPT), *arguments], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, timeout=30)
        lines = done.stdout.splitlines()
        if not lines:
            raise AssertionError("release command produced no stdout: " + done.stderr)
        return done.returncode, json.loads(lines[-1]), done.stdout


class ReleaseCommandTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)

    def assert_report(self, result, step, version, status, code):
        actual_code, report, stdout = result
        self.assertEqual(actual_code, code, stdout)
        self.assertEqual(report["schema"], "agent-relay.release/v1")
        self.assertEqual(report["step"], step)
        self.assertEqual(report["version"], version)
        self.assertEqual(report["status"], status)
        self.assertGreater(len(stdout.splitlines()), 1)
        self.assertRegex("\n".join(stdout.splitlines()[:-1]), r"[\u4e00-\u9fff]")
        return report

    def test_unknown_subcommand_is_usage_refusal(self):
        report = self.assert_report(self.fixture.run_release("unknown"), None, None, "refused", 2)
        self.assertEqual(report["reason"], "usage")

    def test_missing_version_is_usage_refusal(self):
        for step in ("prepare", "publish", "install", "upgrade", "smoke", "evidence"):
            with self.subTest(step=step):
                report = self.assert_report(self.fixture.run_release(step), step, None, "refused", 2)
                self.assertEqual(report["reason"], "usage")

    def test_missing_pr_is_usage_refusal(self):
        report = self.assert_report(self.fixture.run_release("check"), "check", None, "refused", 2)
        self.assertEqual(report["reason"], "usage")

    def test_help_also_ends_with_json(self):
        for args, step in ((["--help"], None), (["prepare", "--help"], "prepare")):
            with self.subTest(args=args):
                self.assert_report(self.fixture.run_release(*args), step, None, "ok", 0)

    def test_argument_errors_keep_the_output_contract(self):
        for args, step in (([], None), (["check", "--pr", "not-a-number"], "check"),
                           (["prepare", "--version", self.fixture.version, "--unknown"], "prepare")):
            with self.subTest(args=args):
                code, report, stdout = self.fixture.run_release(*args)
                self.assertEqual(code, 2, stdout)
                self.assertEqual(report["schema"], "agent-relay.release/v1")
                self.assertEqual(report["step"], step)
                self.assertEqual(report["status"], "refused")
                self.assertEqual(report["reason"], "usage")

    def test_invalid_version_is_refused(self):
        for version in ("1.2", "v1.2.3", "1.2.3-rc1", "../1.2.3", "１.2.3", "1.2.3\n"):
            with self.subTest(version=version):
                report = self.assert_report(self.fixture.run_release("prepare", "--version", version),
                                            "prepare", version, "refused", 2)
                self.assertEqual(report["reason"], "invalid-version")

    def test_unexpected_exception_still_has_json_last_line(self):
        release = load_release()
        stdout = io.StringIO()
        with patch.dict(os.environ, self.fixture.env, clear=True), contextlib.redirect_stdout(stdout):
            with patch.object(release, "prepare", side_effect=RuntimeError("forced exception")):
                code = release.main(["prepare", "--version", self.fixture.version])
        report = self.assert_report((code, json.loads(stdout.getvalue().splitlines()[-1]), stdout.getvalue()),
                                    "prepare", self.fixture.version, "failed", 1)
        self.assertEqual(report["error"], "forced exception")

    def test_status_exit_codes(self):
        release = load_release()
        for status, code in (("ok", 0), ("preview", 0), ("refused", 2), ("waiting-on-user", 3), ("failed", 1)):
            with self.subTest(status=status), patch.dict(os.environ, self.fixture.env, clear=True):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout), patch.object(release, "smoke", return_value={"status": status}):
                    actual = release.main(["smoke", "--version", self.fixture.version])
                self.assert_report((actual, json.loads(stdout.getvalue().splitlines()[-1]), stdout.getvalue()),
                                   "smoke", self.fixture.version, status, code)

    def test_unserializable_facts_become_failed_json(self):
        release = load_release()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), patch.object(release, "prepare", return_value={"path": Path("x")}):
            code = release.main(["prepare", "--version", self.fixture.version])
        report = self.assert_report((code, json.loads(stdout.getvalue().splitlines()[-1]), stdout.getvalue()),
                                   "prepare", self.fixture.version, "failed", 1)
        self.assertIn("serializable", report["error"])

    def test_record_preserves_other_steps_and_replaces_one_step(self):
        release = load_release()
        with patch.dict(os.environ, self.fixture.env, clear=True):
            record = release.read_record(self.fixture.version)
            self.assertFalse((self.fixture.state / "release").exists())
            release.write_record(record, "check", {"status": "ok", "mergeCommit": self.fixture.head})
            release.write_record(release.read_record(self.fixture.version), "prepare", {"status": "ok", "files": 9})
            release.write_record(release.read_record(self.fixture.version), "prepare", {"status": "ok", "files": 10})
            found = release.read_record(self.fixture.version)
        self.assertEqual(found["version"], self.fixture.version)
        self.assertEqual(found["steps"], {"check": {"status": "ok", "mergeCommit": self.fixture.head},
                                           "prepare": {"status": "ok", "files": 10}})
        directory = self.fixture.state / "release"
        self.assertEqual(list(directory.iterdir()), [directory / (self.fixture.version + ".json")])
        self.assertEqual(json.loads((directory / (self.fixture.version + ".json")).read_text()), found)

    def test_failed_replace_preserves_record_and_cleans_temporary_file(self):
        release = load_release()
        with patch.dict(os.environ, self.fixture.env, clear=True):
            release.write_record(release.read_record(self.fixture.version), "check", {"status": "ok"})
            record = release.read_record(self.fixture.version)
            with patch.object(release.os, "replace", side_effect=OSError("forced replace failure")):
                with self.assertRaises(OSError):
                    release.write_record(record, "prepare", {"status": "ok"})
            self.assertEqual(release.read_record(self.fixture.version), record)
        self.assertEqual(len(list((self.fixture.state / "release").iterdir())), 1)

    def test_record_helpers_reject_invalid_version_before_writing(self):
        release = load_release()
        with patch.dict(os.environ, self.fixture.env, clear=True):
            for operation in (lambda: release.read_record("../1.2"),
                              lambda: release.write_record({"version": "../1.2"}, "check", {})):
                with self.assertRaises(release.ReleaseError) as caught:
                    operation()
                self.assertEqual(caught.exception.reason, "invalid-version")
        self.assertEqual(list(self.fixture.state.iterdir()), [])

    def test_fixture_tools_log_argv_and_use_json_responses(self):
        for tool in ("gh", "claude", "codex", "ps", "node"):
            self.fixture.answer(tool, ["an argument with spaces"], stdout="fake output\n", stderr="fake error\n",
                                returncode=7)
            done = subprocess.run([tool, "an argument with spaces"], env=self.fixture.env, capture_output=True,
                                  text=True, timeout=30)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (7, "fake output\n", "fake error\n"))
        self.assertEqual(self.fixture.calls(), [[tool, "an argument with spaces"]
                                               for tool in ("gh", "claude", "codex", "ps", "node")])
        self.assertEqual(self.fixture.git("rev-parse", "origin/main"), self.fixture.head)


class ReleaseCheckTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)
        self.addCleanup(self.assert_no_writes)
        self.set_gh()

    def set_gh(self, merged=True, runs=None):
        self.fixture.answer("gh", ["api", "repos/example/agent-relay/pulls/7"],
                            stdout=json.dumps({"merged": merged, "merge_commit_sha": self.fixture.head}))
        if runs is None:
            runs = [{"conclusion": "success", "status": "completed", "workflowName": "CI"}]
        self.fixture.answer("gh", ["run", "list", "--repo", "example/agent-relay", "--commit", self.fixture.head,
                                   "--json", "conclusion,status,workflowName"], stdout=json.dumps(runs))

    def commit_release(self, files):
        self.fixture.head = self.fixture.commit(files)
        self.fixture.git("push", "-q", "origin", "main")
        self.set_gh()

    def check(self, reason=None):
        code, report, stdout = self.fixture.run_release("check", "--pr", "7", "--github", "example/agent-relay")
        self.assertEqual(code, 2 if reason else 0, stdout)
        self.assertEqual(report["schema"], "agent-relay.release/v1")
        self.assertEqual(report["step"], "check")
        self.assertEqual(report["status"], "refused" if reason else "ok", stdout)
        self.assertRegex("\n".join(stdout.splitlines()[:-1]), r"[\u4e00-\u9fff]")
        if reason:
            self.assertEqual(report["reason"], reason, stdout)
            self.assertEqual(list(self.fixture.state.iterdir()), [])
        else:
            self.assertEqual(report["version"], self.fixture.version)
        return report

    def assert_no_writes(self):
        for call in self.fixture.calls():
            if call[0] == "git":
                args = call[1:]
                if args[:1] == ["-C"]:
                    args = args[2:]
                self.assertNotEqual(args[:1], ["push"], call)
                if args[:1] == ["tag"]:
                    self.assertTrue("--merged" in args or "--list" in args, call)
            self.assertNotEqual(call[:2], ["gh", "release"], call)

    def test_not_merged(self):
        self.set_gh(merged=False)
        self.check("not-merged")

    def test_main_moved_after_merge(self):
        self.fixture.commit({"later.txt": "A later main commit.\n"})
        self.fixture.git("push", "-q", "origin", "main")
        self.check("main-moved")

    def test_ci_empty(self):
        self.set_gh(runs=[])
        self.check("ci-not-green")

    def test_ci_in_progress(self):
        self.set_gh(runs=[{"status": "in_progress", "conclusion": None, "workflowName": "CI"}])
        self.check("ci-not-green")

    def test_ci_one_failure(self):
        self.set_gh(runs=[{"status": "completed", "conclusion": "success", "workflowName": "CI"},
                          {"status": "completed", "conclusion": "failure", "workflowName": "Other CI"}])
        self.check("ci-not-green")

    def test_plugin_versions_differ(self):
        self.commit_release({"plugins/agent-relay/.codex-plugin/plugin.json": '{"version": "1.2.2"}'})
        self.check("version-mismatch")

    def test_plugin_version_invalid(self):
        self.commit_release({name: '{"version": "1.2"}' for name in (
            "plugins/agent-relay/.claude-plugin/plugin.json", "plugins/agent-relay/.codex-plugin/plugin.json")})
        self.check("version-mismatch")

    def test_zh_readme_missing_ref(self):
        self.commit_release({"README.md": "> 状态：1.2.3（接口 2.11）\n安装：--ref v1.2.2\n"})
        self.check("readme-mismatch")

    def test_en_readme_status_mismatch(self):
        self.commit_release({"README.en.md": "> Status: 1.2.2 (interface 2.11)\nInstall: --ref v1.2.3\n"})
        self.check("readme-mismatch")

    def test_changelog_missing_section(self):
        self.commit_release({"CHANGELOG.md": "# Changelog\n\n## [1.2.30]\n\nWrong version.\n"})
        self.check("changelog-missing")

    def test_bridge_version_higher(self):
        self.commit_release({"plugins/agent-relay/bridge/package.json": '{"version": "1.10.0"}'})
        self.check("bridge-version")

    def test_tag_exists_locally(self):
        self.fixture.git("tag", "v1.2.3")
        self.check("tag-exists")

    def test_tag_exists_only_on_remote(self):
        self.fixture.git("config", "remote.origin.tagOpt", "--no-tags")
        old_head = self.fixture.git("rev-parse", "HEAD")
        self.commit_release({"release.txt": "Release metadata.\n"})
        self.fixture.git("tag", "-a", "v1.2.3", old_head, "-m", "Existing remote tag")
        self.fixture.git("push", "-q", "origin", "v1.2.3")
        self.fixture.git("tag", "-d", "v1.2.3")
        self.assertEqual(self.fixture.git("tag", "--list", "v1.2.3"), "")
        self.check("tag-exists")
        self.assertEqual(self.fixture.git("tag", "--list", "v1.2.3"), "")

    def test_ok_records_every_fact_from_merge_commit(self):
        self.fixture.git("tag", "v1.2.2")
        self.commit_release({"plugins/agent-relay/bridge/src/x.ts": "export const x = 2;\n",
                             "plugins/agent-relay/interface.json": '{"interface": "2.12"}'})
        # A dirty working tree must not affect the facts read from the merge commit.
        (self.fixture.repo / "README.md").write_text("Not the release README.\n", encoding="utf-8")
        report = self.check()
        facts = {"status": "ok", "mergeCommit": self.fixture.head, "previousTag": "v1.2.2",
                 "interface": {"from": "2.11", "to": "2.12"}, "runtimeUpgrade": True,
                 "runtimeFiles": ["src/x.ts"]}
        self.assertEqual(report, {"schema": "agent-relay.release/v1", "step": "check",
                                  "version": self.fixture.version, **facts})
        record = json.loads((self.fixture.state / "release" / "1.2.3.json").read_text())
        self.assertEqual(record, {"schema": "agent-relay.release/v1", "version": self.fixture.version,
                                  "steps": {"check": facts}})
        calls = self.fixture.calls()
        self.assertIn(["gh", "api", "repos/example/agent-relay/pulls/7"], calls)
        self.assertIn(["gh", "run", "list", "--repo", "example/agent-relay", "--commit", self.fixture.head,
                       "--json", "conclusion,status,workflowName"], calls)
        git_calls = [call[3:] for call in calls if call[0] == "git"]
        self.assertIn(["fetch", "origin"], git_calls)
        self.assertIn(["show", self.fixture.head + ":README.md"], git_calls)

    def test_without_previous_tag_requires_runtime_upgrade(self):
        report = self.check()
        self.assertIsNone(report["previousTag"])
        self.assertEqual(report["interface"], {"from": None, "to": "2.11"})
        self.assertIs(report["runtimeUpgrade"], True)
        self.assertEqual(report["runtimeFiles"], ["package.json", "src/x.ts"])

    def test_test_only_change_needs_no_runtime_upgrade(self):
        self.fixture.git("tag", "v1.2.2")
        self.commit_release({"plugins/agent-relay/bridge/test/x.test.ts": "// Changed test only.\n"})
        report = self.check()
        self.assertIs(report["runtimeUpgrade"], False)
        self.assertEqual(report["runtimeFiles"], [])

    def test_source_change_needs_runtime_upgrade(self):
        self.fixture.git("tag", "v1.2.2")
        self.commit_release({"plugins/agent-relay/bridge/src/nested/new.ts": "export const x = 2;\n"})
        report = self.check()
        self.assertIs(report["runtimeUpgrade"], True)
        self.assertEqual(report["runtimeFiles"], ["src/nested/new.ts"])

    def test_runtime_file_names_match_exactly(self):
        self.fixture.git("tag", "v1.2.2")
        self.commit_release({"plugins/agent-relay/bridge/package.json.bak": "Not a runtime file.\n",
                             "plugins/agent-relay/bridge/tsconfig.json": "{}\n"})
        report = self.check()
        self.assertEqual(report["runtimeFiles"], ["tsconfig.json"])

    def test_previous_tag_uses_highest_merged_version(self):
        for tag in ("v1.2.9", "v1.2.10", "unrelated"):
            self.fixture.git("tag", tag)
        self.commit_release({"release.txt": "A new release.\n"})
        self.fixture.git("checkout", "-q", "-b", "unmerged", "HEAD~1")
        side = self.fixture.commit({"side.txt": "An unmerged commit.\n"})
        self.fixture.git("tag", "v9.0.0", side)
        self.fixture.git("checkout", "-q", "main")
        self.assertEqual(self.check()["previousTag"], "v1.2.10")


class ReleasePrepareTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)
        self.addCleanup(self.assert_local_calls)
        self.release = load_release()

    def assert_local_calls(self):
        for call in self.fixture.calls():
            self.assertEqual(call[:3], ["git", "-C", str(self.fixture.repo)], call)
            self.assertIn(call[3], ("archive", "show"), call)

    def record_check(self, status="ok"):
        with patch.dict(os.environ, self.fixture.env, clear=True):
            return self.release.write_record(self.release.read_record(self.fixture.version), "check",
                                             {"status": status, "mergeCommit": self.fixture.head})

    def prepare(self):
        code, report, stdout = self.fixture.run_release("prepare", "--version", self.fixture.version)
        self.assertEqual(code, 0, stdout)
        self.assertEqual(report["schema"], "agent-relay.release/v1")
        self.assertEqual(report["step"], "prepare")
        self.assertEqual(report["version"], self.fixture.version)
        self.assertEqual(report["status"], "ok", stdout)
        directory = Path(report["dir"])
        self.addCleanup(shutil.rmtree, directory)
        self.assertTrue(directory.name.startswith("agent-relay-release-"))
        return report, directory

    def test_prepare_needs_recorded_check_ok(self):
        for status in (None, "refused", "failed", "preview", "waiting-on-user"):
            with self.subTest(status=status):
                if status is not None:
                    self.record_check(status)
                code, report, stdout = self.fixture.run_release("prepare", "--version", self.fixture.version)
                self.assertEqual(code, 2, stdout)
                self.assertEqual(report["status"], "refused")
                self.assertEqual(report["reason"], "needs-check")
                with patch.dict(os.environ, self.fixture.env, clear=True):
                    self.assertNotIn("prepare", self.release.read_record(self.fixture.version)["steps"])
        self.assertEqual(self.fixture.calls(), [])

    def test_prepare_archives_checked_commit_and_records_sorted_manifest(self):
        plugin = "plugins/agent-relay/"
        binary = self.fixture.repo / plugin / "binary.dat"
        binary.write_bytes(bytes(range(256)))
        self.fixture.head = self.fixture.commit({
            plugin + "z-last.txt": "Last.\n", plugin + "a-first.txt": "中文内容\n",
            plugin + ".DS_Store": "Ignored file.\n",
            plugin + "bridge/node_modules/dependency.js": "Ignored dependency.\n",
            plugin + "hooks/__pycache__/cache.pyc": "Ignored cache.\n",
            plugin + ".codex-plugin/migrated-command-skills/generated.md": "Ignored skill.\n",
        })
        before = self.record_check()
        # Both a later commit and dirty files must be absent from the prepared tree.
        self.fixture.commit({plugin + "later.txt": "Not checked.\n", "CHANGELOG.md": "Later notes.\n"})
        binary.write_bytes(b"Dirty binary.\n")
        report, directory = self.prepare()
        tracked = self.fixture.git("ls-tree", "-r", "--name-only", self.fixture.head, "--",
                                   ".claude-plugin", "plugins/agent-relay").splitlines()
        actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
        self.assertEqual(actual, set(tracked) | {"MANIFEST.json", "release-notes.md"})
        self.assertEqual({path.name for path in directory.iterdir()},
                         {".claude-plugin", "plugins", "MANIFEST.json", "release-notes.md"})
        self.assertEqual({path.name for path in (directory / "plugins").iterdir()}, {"agent-relay"})
        expected = {}
        for name in tracked:
            contents = subprocess.run([REAL_GIT, "-C", str(self.fixture.repo), "show",
                                       self.fixture.head + ":" + name], env=self.fixture.env,
                                      capture_output=True, check=True, timeout=30).stdout
            self.assertEqual((directory / name).read_bytes(), contents)
            relative = Path(name).relative_to("plugins/agent-relay") if name.startswith(plugin) else None
            if relative is not None and not any(part in self.release._preflight.IGNORED for part in relative.parts):
                expected[relative.as_posix()] = hashlib.sha256(contents).hexdigest()
        manifest_path = directory / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest, expected)
        self.assertEqual(list(manifest), sorted(expected))
        self.assertEqual(report["manifestSha256"], hashlib.sha256(manifest_path.read_bytes()).hexdigest())
        self.assertEqual(report["files"], len(expected))
        self.assertEqual((directory / "release-notes.md").read_text(encoding="utf-8"),
                         "\nRelease test notes.\n\n")
        with patch.dict(os.environ, self.fixture.env, clear=True):
            self.assertEqual(self.release.read_record(self.fixture.version)["steps"],
                             {**before["steps"], "prepare": {key: value for key, value in report.items()
                                                            if key not in ("schema", "step", "version")}})
        self.assertIn(["git", "-C", str(self.fixture.repo), "archive", "--format=tar", self.fixture.head,
                       ".claude-plugin", "plugins/agent-relay"], self.fixture.calls())

    def test_prepare_notes_at_end_of_changelog_and_rerun_uses_fresh_directory(self):
        notes = "\n### Fixed\n\n- 修复内容。  \n"
        self.fixture.head = self.fixture.commit({
            "CHANGELOG.md": "# Changelog\n\n## [1.2.4]\n\nNewer notes.\n\n## [1.2.3] - 2026-01-01\n" + notes})
        self.record_check()
        first, first_dir = self.prepare()
        second, second_dir = self.prepare()
        self.assertNotEqual(first_dir, second_dir)
        self.assertEqual(first["manifestSha256"], second["manifestSha256"])
        for directory in (first_dir, second_dir):
            self.assertEqual((directory / "release-notes.md").read_text(encoding="utf-8"), notes)
        with patch.dict(os.environ, self.fixture.env, clear=True):
            self.assertEqual(self.release.read_record(self.fixture.version)["steps"]["prepare"]["dir"], str(second_dir))

    def test_prepare_empty_notes_without_trailing_newline(self):
        self.fixture.head = self.fixture.commit({"CHANGELOG.md": "# Changelog\n\n## [1.2.3]"})
        self.record_check()
        _, directory = self.prepare()
        self.assertEqual((directory / "release-notes.md").read_bytes(), b"")

    def test_prepare_refuses_absolute_and_parent_archive_paths_before_extraction(self):
        self.record_check()
        for name in ("/outside.txt", "../outside.txt", "plugins/../outside.txt"):
            with self.subTest(name=name):
                contents = io.BytesIO()
                with tarfile.open(fileobj=contents, mode="w") as archive:
                    archive.addfile(tarfile.TarInfo("safe.txt"))
                    archive.addfile(tarfile.TarInfo(name))
                destination = self.fixture.root / "prepared"
                destination.mkdir(exist_ok=True)
                stdout = io.StringIO()
                answer = subprocess.CompletedProcess([], 0, stdout=contents.getvalue())
                with patch.dict(os.environ, self.fixture.env, clear=True), contextlib.redirect_stdout(stdout):
                    with patch.object(self.release, "run", return_value=answer), \
                            patch.object(self.release.tempfile, "mkdtemp", return_value=str(destination)):
                        code = self.release.main(["prepare", "--repo", str(self.fixture.repo),
                                                  "--version", self.fixture.version])
                report = json.loads(stdout.getvalue().splitlines()[-1])
                self.assertEqual(code, 2, stdout.getvalue())
                self.assertEqual(report["status"], "refused")
                self.assertEqual(report["reason"], "unsafe-archive")
                self.assertEqual(list(destination.iterdir()), [])
                with patch.dict(os.environ, self.fixture.env, clear=True):
                    self.assertNotIn("prepare", self.release.read_record(self.fixture.version)["steps"])


class ReleasePublishTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)
        self.release = load_release()
        with patch.dict(os.environ, self.fixture.env, clear=True):
            self.release.write_record(self.release.read_record(self.fixture.version), "check", {
                "status": "ok", "mergeCommit": self.fixture.head, "interface": {"from": None, "to": "2.11"}})
        code, report, stdout = self.fixture.run_release("prepare", "--version", self.fixture.version)
        self.assertEqual(code, 0, stdout)
        self.directory = Path(report["dir"])
        self.addCleanup(shutil.rmtree, self.directory)
        self.record_path = self.fixture.state / "release" / (self.fixture.version + ".json")
        self.tag = "v" + self.fixture.version
        self.url = "https://github.com/example/agent-relay/releases/tag/" + self.tag
        self.create = ["gh", "release", "create", self.tag, "--verify-tag", "--title",
                       "agent-relay 1.2.3 (interface 2.11)", "--notes-file",
                       str(self.directory / "release-notes.md"), "--repo", "example/agent-relay"]
        self.view = ["gh", "release", "view", self.tag, "--json", "url", "--jq", ".url",
                     "--repo", "example/agent-relay"]
        self.fixture.answer("gh", self.create[1:], stdout=self.url + "\n")
        self.fixture.answer("gh", self.view[1:], returncode=1)
        self.fixture.calls_log.write_text("", encoding="utf-8")

    def publish(self, *args, status="ok", reason=None):
        code, report, stdout = self.fixture.run_release(
            "publish", "--version", self.fixture.version, "--github", "example/agent-relay", *args)
        self.assertEqual(code, {"ok": 0, "preview": 0, "refused": 2, "failed": 1}[status], stdout)
        self.assertEqual(report["schema"], "agent-relay.release/v1")
        self.assertEqual(report["step"], "publish")
        self.assertEqual(report["version"], self.fixture.version)
        self.assertEqual(report["status"], status, stdout)
        if reason:
            self.assertEqual(report["reason"], reason, stdout)
        return report

    def writes(self):
        writes = []
        for call in self.fixture.calls():
            if call[0] == "git" and call[3] in ("tag", "push"):
                writes.append(call)
            elif call[:3] == ["gh", "release", "create"]:
                writes.append(call)
        return writes

    def test_publish_needs_recorded_check_and_prepare_ok(self):
        original = json.loads(self.record_path.read_text())
        for step in ("check", "prepare"):
            for status in (None, "preview", "refused", "failed", "waiting-on-user"):
                with self.subTest(step=step, status=status):
                    record = json.loads(json.dumps(original))
                    if status is None:
                        del record["steps"][step]
                    else:
                        record["steps"][step]["status"] = status
                    self.record_path.write_text(json.dumps(record), encoding="utf-8")
                    before = self.record_path.read_bytes()
                    self.publish("--confirm", status="refused", reason="needs-" + step)
                    self.assertEqual(self.record_path.read_bytes(), before)
        self.assertEqual(self.fixture.calls(), [])

    def test_publish_preview_lists_three_commands_without_writes(self):
        before = self.record_path.read_bytes()
        refs = self.fixture.git("show-ref")
        report = self.publish(status="preview")
        self.assertEqual(report["commands"], [
            ["git", "-C", str(self.fixture.repo), "tag", "-a", self.tag, self.fixture.head,
             "-m", "agent-relay 1.2.3"],
            ["git", "-C", str(self.fixture.repo), "push", "origin", self.tag], self.create])
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.fixture.git("show-ref"), refs)
        self.assertEqual(self.fixture.git("ls-remote", "origin", "refs/tags/" + self.tag), "")
        self.assertEqual(self.record_path.read_bytes(), before)

    def test_publish_confirm_creates_annotated_tag_and_release_in_order(self):
        before = json.loads(self.record_path.read_text())
        # Publication must use the recorded merge commit even when local HEAD is later.
        self.fixture.commit({"later.txt": "Not the release commit.\n"})
        report = self.publish("--confirm")
        self.assertEqual(self.fixture.git("-C", str(self.fixture.remote), "cat-file", "-t",
                                          "refs/tags/" + self.tag), "tag")
        self.assertEqual(self.fixture.git("-C", str(self.fixture.remote), "rev-parse", self.tag + "^{}"),
                         self.fixture.head)
        self.assertEqual(report["tag"], self.tag)
        self.assertEqual(report["releaseUrl"], self.url)
        self.assertEqual(report["peeledCommit"], self.fixture.head)
        writes = self.writes()
        self.assertEqual([call[3] if call[0] == "git" else call[2] for call in writes],
                         ["tag", "push", "create"])
        self.assertEqual(writes[-1], self.create)
        self.assertEqual(self.fixture.calls()[-1], ["git", "-C", str(self.fixture.repo), "ls-remote",
                                                   "origin", "refs/tags/" + self.tag + "^{}"])
        record = json.loads(self.record_path.read_text())
        self.assertEqual(record["steps"]["check"], before["steps"]["check"])
        self.assertEqual(record["steps"]["prepare"], before["steps"]["prepare"])
        self.assertEqual(record["steps"]["publish"], {key: value for key, value in report.items()
                                                    if key not in ("schema", "step", "version")})

    def test_publish_refuses_when_remote_main_moved(self):
        before = self.record_path.read_bytes()
        later = self.fixture.commit({"later.txt": "Remote main moved.\n"})
        self.fixture.git("push", "-q", "origin", "HEAD:refs/heads/later")
        self.fixture.git("-C", str(self.fixture.remote), "update-ref", "refs/heads/main", later)
        self.assertEqual(self.fixture.git("rev-parse", "origin/main"), self.fixture.head)
        for args in ((), ("--confirm",)):
            with self.subTest(args=args):
                self.publish(*args, status="refused", reason="main-moved")
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.record_path.read_bytes(), before)

    def test_publish_rerun_is_ok_without_any_writes(self):
        self.publish("--confirm")
        self.fixture.answer("gh", self.view[1:], stdout=self.url + "\n")
        before = self.record_path.read_bytes()
        refs = self.fixture.git("show-ref")
        self.fixture.calls_log.write_text("", encoding="utf-8")
        for args in ((), ("--confirm",)):
            with self.subTest(args=args):
                report = self.publish(*args)
                self.assertIs(report["alreadyPublished"], True)
                self.assertEqual(report["releaseUrl"], self.url)
                self.assertEqual(report["peeledCommit"], self.fixture.head)
        self.assertIn(self.view, self.fixture.calls())
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.fixture.git("show-ref"), refs)
        self.assertEqual(self.record_path.read_bytes(), before)

    def test_publish_refuses_remote_tag_at_another_commit(self):
        before = self.record_path.read_bytes()
        other = self.fixture.commit({"other.txt": "Wrong release commit.\n"})
        for annotated in (False, True):
            with self.subTest(annotated=annotated):
                args = ["tag", "-f"] + (["-a", "-m", "Wrong tag"] if annotated else [])
                self.fixture.git(*args, self.tag, other)
                self.fixture.git("push", "-q", "--force", "origin", self.tag)
                for confirm in ((), ("--confirm",)):
                    self.publish(*confirm, status="refused", reason="tag-mismatch")
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.record_path.read_bytes(), before)

    def test_publish_fails_when_remote_tag_changes_after_create(self):
        other = self.fixture.commit({"other.txt": "Unexpected remote tag target.\n"})
        before = self.record_path.read_bytes()
        original_run = self.release.run

        def run_with_moved_tag(args, *positional, **kwargs):
            result = original_run(args, *positional, **kwargs)
            if args[:3] == ["gh", "release", "create"]:
                self.fixture.git("tag", "-a", "unexpected", other, "-m", "Changed remote tag")
                self.fixture.git("push", "-q", "--force", "origin",
                                 "refs/tags/unexpected:refs/tags/" + self.tag)
            return result

        stdout = io.StringIO()
        with patch.dict(os.environ, self.fixture.env, clear=True), contextlib.redirect_stdout(stdout):
            with patch.object(self.release, "run", side_effect=run_with_moved_tag):
                code = self.release.main(["publish", "--repo", str(self.fixture.repo), "--version",
                                          self.fixture.version, "--github", "example/agent-relay", "--confirm"])
        report = json.loads(stdout.getvalue().splitlines()[-1])
        self.assertEqual(code, 1, stdout.getvalue())
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["reason"], "tag-mismatch")
        self.assertEqual(self.record_path.read_bytes(), before)


class ReleaseInstallTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)
        self.release = load_release()
        self.marketplaces = self.fixture.claude / "plugins" / "known_marketplaces.json"
        self.marketplaces.parent.mkdir()
        self.config = self.fixture.codex / "config.toml"
        self.url = "https://github.com/example/agent-relay.git"
        self.git_config = ('[marketplaces.agent-relay-marketplace]\n'
                           'source = "' + self.url + '"\nref = "main"\n')
        self.config.write_bytes(self.git_config.encode())
        self.claude_source = {"source": "git", "url": self.url, "ref": "main"}
        self.write_marketplace(self.claude_source)
        with patch.dict(os.environ, self.fixture.env, clear=True):
            self.release.write_record(self.release.read_record(self.fixture.version), "publish", {
                "status": "ok", "tag": "v" + self.fixture.version, "peeledCommit": self.fixture.head})
        self.record_path = self.fixture.state / "release" / (self.fixture.version + ".json")

    def write_marketplace(self, source):
        self.marketplaces.write_text(json.dumps({
            "other": {"source": {"source": "directory", "path": "/unrelated"}},
            "agent-relay-marketplace": {"source": source, "installLocation": "/unused-cache"},
        }, indent=2) + "\n", encoding="utf-8")

    def install(self, *args, status="preview", reason=None):
        code, report, stdout = self.fixture.run_release("install", "--version", self.fixture.version, *args)
        self.assertEqual(code, {"preview": 0, "refused": 2}[status], stdout)
        self.assertEqual(report["schema"], "agent-relay.release/v1")
        self.assertEqual(report["step"], "install")
        self.assertEqual(report["version"], self.fixture.version)
        self.assertEqual(report["status"], status, stdout)
        if reason:
            self.assertEqual(report["reason"], reason, stdout)
        return report

    def test_claude_source_detects_directory_git_and_github(self):
        cases = [
            ({"source": "directory", "path": str(self.fixture.repo)},
             {"kind": "directory", "path": str(self.fixture.repo)}),
            (self.claude_source, {"kind": "git", "url": self.url, "ref": "main"}),
            ({"source": "github", "repo": "example/agent-relay"},
             {"kind": "git", "repo": "example/agent-relay"}),
        ]
        for source, expected in cases:
            with self.subTest(source=source), patch.dict(os.environ, self.fixture.env, clear=True):
                self.write_marketplace(source)
                before = self.marketplaces.read_bytes()
                self.assertEqual(self.release.claude_source(), expected)
                self.assertEqual(self.marketplaces.read_bytes(), before)
        self.assertEqual(self.fixture.calls(), [])

    def test_codex_ref_change_preserves_every_other_byte_and_line_ending(self):
        for newline in ("\n", "\r\n"):
            for trailing in ("", newline):
                for last_ref in (False, True):
                    with self.subTest(newline=newline, trailing=trailing, last_ref=last_ref):
                        prefix = ('# 注释 and unrelated ref\n[marketplaces.other]\nref = "other"\n'
                                  '[marketplaces.agent-relay-marketplace] # target [comment]\n'
                                  '# ref = "comment"\nsource = "' + self.url + '"\n')
                        suffix = "" if last_ref else '\n# keep this comment\n[other]\nref = "untouched"'
                        old = '\t  ref  = "main" # old pin'
                        text = (prefix + old + suffix).replace("\n", newline) + trailing
                        expected = text.replace(old, '\t  ref = "v1.2.3"')
                        self.assertEqual(self.release.codex_ref_change(text, self.fixture.version).encode(),
                                         expected.encode())

    def test_codex_ref_change_refuses_missing_or_ambiguous_ref(self):
        cases = [
            '[marketplaces.other]\nsource = "' + self.url + '"\nref = "main"\n',
            self.git_config + 'ref = "another"\n',
            self.git_config.replace('ref = "main"\n', '# ref = "comment only"\n'),
        ]
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(self.release.ReleaseError) as caught:
                    self.release.codex_ref_change(text, self.fixture.version)
                self.assertEqual(caught.exception.status, "refused")
                self.assertEqual(caught.exception.reason, "codex-ref-ambiguous")

    def test_codex_local_path_source_needs_no_ref_change(self):
        for key in ("source", "path"):
            with self.subTest(key=key):
                text = '[marketplaces.agent-relay-marketplace]\n' + key + ' = "' + str(self.fixture.repo) + '"\n'
                self.assertIsNone(self.release.codex_ref_change(text, self.fixture.version))
                self.config.write_bytes(text.encode())
                report = self.install()
                self.assertEqual(report["sources"]["codex"], {"kind": "directory", "path": str(self.fixture.repo)})
                self.assertEqual(self.config.read_bytes(), text.encode())

    def test_install_needs_recorded_publish_ok(self):
        for status in (None, "preview", "refused", "failed", "waiting-on-user"):
            for confirm in ((), ("--confirm",)):
                with self.subTest(status=status, confirm=confirm):
                    record = {"schema": self.release.SCHEMA, "version": self.fixture.version, "steps": {}}
                    if status is not None:
                        record["steps"]["publish"] = {"status": status}
                    self.record_path.write_text(json.dumps(record), encoding="utf-8")
                    before = self.record_path.read_bytes()
                    self.install(*confirm, status="refused", reason="needs-publish")
                    self.assertEqual(self.record_path.read_bytes(), before)
        self.assertEqual(self.fixture.calls(), [])

    def test_install_preview_lists_sources_and_exact_commands_without_changes(self):
        for directory in (False, True):
            with self.subTest(directory=directory):
                source = {"source": "directory", "path": str(self.fixture.repo)} if directory else self.claude_source
                self.write_marketplace(source)
                # Exercise raw decoding as well as the pure function's CRLF preservation.
                self.config.write_bytes(self.git_config.replace("\n", "\r\n").encode())
                paths = (self.config, self.marketplaces, self.record_path)
                before = {path: path.read_bytes() for path in paths}
                refs = self.fixture.git("show-ref")
                report = self.install()
                self.assertEqual(report["sources"]["claude"],
                                 {"kind": "directory", "path": str(self.fixture.repo)} if directory else
                                 {"kind": "git", "url": self.url, "ref": "main"})
                self.assertEqual(report["sources"]["codex"], {"kind": "git", "url": self.url, "ref": "main"})
                commands = [["git", "-C", str(self.fixture.repo), "pull", "--ff-only"]] if directory else []
                commands += [
                    ["claude", "plugin", "marketplace", "update", "agent-relay-marketplace"],
                    ["claude", "plugin", "update", "--scope", "user", "agent-relay@agent-relay-marketplace"],
                    ["codex", "plugin", "add", "agent-relay@agent-relay-marketplace"],
                ]
                self.assertEqual(report["commands"], commands)
                self.assertEqual(report["codexConfig"], {
                    "path": str(self.config),
                    "backup": str(self.record_path.parent / "1.2.3-config.toml.bak"),
                    "refChange": True, "ref": "v1.2.3"})
                self.assertEqual({path: path.read_bytes() for path in paths}, before)
                self.assertEqual(self.fixture.git("show-ref"), refs)
                self.assertEqual(self.fixture.git("status", "--porcelain"), "")
                self.assertEqual(sorted(path.name for path in self.record_path.parent.iterdir()), ["1.2.3.json"])
        self.assertEqual(self.fixture.calls(), [])

    def test_install_preview_refuses_ambiguous_config_without_changes(self):
        for text in ('# missing section\n', self.git_config + 'ref = "second"\n',
                     self.git_config.replace('ref = "main"\n', '')):
            with self.subTest(text=text):
                self.config.write_bytes(text.encode())
                paths = (self.config, self.marketplaces, self.record_path)
                before = {path: path.read_bytes() for path in paths}
                self.install(status="refused", reason="codex-ref-ambiguous")
                self.assertEqual({path: path.read_bytes() for path in paths}, before)
        self.assertEqual(self.fixture.calls(), [])


class ReleaseInstallConfirmTests(unittest.TestCase):
    """D282 second half: run the host commands in order, then verify each host copy file by file."""

    PLUGIN_ID = "agent-relay@agent-relay-marketplace"

    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)
        self.release = load_release()
        self.record_path = self.fixture.state / "release" / (self.fixture.version + ".json")
        self.backup = self.fixture.state / "release" / (self.fixture.version + "-config.toml.bak")
        self.url = "https://github.com/example/agent-relay.git"
        self.config = self.fixture.codex / "config.toml"
        self.git_config = ('# keep\n[marketplaces.agent-relay-marketplace]\n'
                           'source = "' + self.url + '"\nref = "main"\n\n[other]\nref = "x"\n')
        self.config.write_bytes(self.git_config.encode())
        self.marketplaces = self.fixture.claude / "plugins" / "known_marketplaces.json"
        self.marketplaces.parent.mkdir()
        self.claude_copy = self.fixture.root / "claude-copy"
        self.codex_copy = (self.fixture.codex / "plugins" / "cache" / "agent-relay-marketplace" / "agent-relay"
                           / self.fixture.version)
        self.write_marketplace({"source": "git", "url": self.url})
        self.write_installed(self.claude_copy)
        self.fixture.answer("codex", ["plugin", "list", "--json"], stdout=json.dumps({"installed": [
            {"name": "other", "pluginId": "other@x", "version": "9.9.9"},
            {"name": "agent-relay", "pluginId": self.PLUGIN_ID, "version": self.fixture.version, "enabled": True},
        ]}))
        self.release_at(self.fixture.head)

    def release_at(self, sha):
        """Record check, a real prepare of `sha`, and publish; then lay down matching host copies."""
        with patch.dict(os.environ, self.fixture.env, clear=True):
            self.release.write_record(self.release.read_record(self.fixture.version), "check", {
                "status": "ok", "mergeCommit": sha, "interface": {"from": None, "to": "2.11"}})
        code, report, stdout = self.fixture.run_release("prepare", "--version", self.fixture.version)
        self.assertEqual(code, 0, stdout)
        self.prepared = Path(report["dir"])
        self.addCleanup(shutil.rmtree, self.prepared, True)
        with patch.dict(os.environ, self.fixture.env, clear=True):
            self.release.write_record(self.release.read_record(self.fixture.version), "publish", {
                "status": "ok", "tag": "v" + self.fixture.version, "peeledCommit": sha})
        for copy in (self.claude_copy, self.codex_copy):
            if copy.exists():
                shutil.rmtree(copy)
            shutil.copytree(self.prepared / "plugins" / "agent-relay", copy)
        self.fixture.calls_log.write_text("", encoding="utf-8")

    def write_marketplace(self, source):
        self.marketplaces.write_text(json.dumps({
            "agent-relay-marketplace": {"source": source, "installLocation": "/unused-cache"}}) + "\n",
            encoding="utf-8")

    def write_installed(self, path):
        (self.fixture.claude / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {
            self.PLUGIN_ID: [
                {"scope": "local", "installPath": "/not-this-one", "version": "0.0.1"},
                {"scope": "user", "installPath": str(path), "version": self.fixture.version},
            ]}}), encoding="utf-8")

    def make_clone(self):
        clone = self.fixture.root / "clone"
        subprocess.run([REAL_GIT, "clone", "-q", str(self.fixture.remote), str(clone)], env=self.fixture.env,
                       capture_output=True, check=True, timeout=30)
        self.write_marketplace({"source": "directory", "path": str(clone)})
        return clone

    def clone_git(self, clone, *args):
        return subprocess.run([REAL_GIT, "-c", "core.hooksPath=" + os.devnull, "-C", str(clone), *args],
                              env=self.fixture.env, capture_output=True, text=True, check=True,
                              timeout=30).stdout.strip()

    def install(self, status="ok", reason=None):
        code, report, stdout = self.fixture.run_release("install", "--version", self.fixture.version, "--confirm")
        self.assertEqual(code, {"ok": 0, "refused": 2, "failed": 1}[status], stdout)
        self.assertEqual(report["schema"], "agent-relay.release/v1")
        self.assertEqual(report["step"], "install")
        self.assertEqual(report["version"], self.fixture.version)
        self.assertEqual(report["status"], status, stdout)
        if reason:
            self.assertEqual(report["reason"], reason, stdout)
        return report, stdout

    def writes(self):
        """Every call that changes a clone or a host, in order."""
        found = []
        for call in self.fixture.calls():
            if call[0] == "git" and "pull" in call:
                found.append("pull")
            elif call[:3] == ["claude", "plugin", "marketplace"]:
                found.append("claude marketplace update")
            elif call[:3] == ["claude", "plugin", "update"]:
                found.append("claude plugin update")
            elif call[:3] == ["codex", "plugin", "add"]:
                found.append("codex plugin add")
            elif call[0] in ("claude", "codex") and call[1:] != ["plugin", "list", "--json"]:
                found.append(" ".join(call))
        return found

    def test_confirm_runs_host_commands_in_order_and_records_both_copies(self):
        # Files hosts add to their own copies are never compared (preflight.IGNORED).
        (self.codex_copy / "migrated-command-skills").mkdir()
        (self.codex_copy / "migrated-command-skills" / "x.md").write_text("added by Codex\n", encoding="utf-8")
        (self.claude_copy / "bridge" / "node_modules").mkdir()
        (self.claude_copy / "bridge" / "node_modules" / "dep.js").write_text("built\n", encoding="utf-8")
        report, stdout = self.install()
        self.assertEqual(self.fixture.calls(), [
            ["claude", "plugin", "marketplace", "update", "agent-relay-marketplace"],
            ["claude", "plugin", "update", "--scope", "user", self.PLUGIN_ID],
            ["codex", "plugin", "add", self.PLUGIN_ID],
            ["codex", "plugin", "list", "--json"],
        ])
        # The backup holds the pre-change bytes, so it was taken before the edit.
        self.assertEqual(self.backup.read_bytes(), self.git_config.encode())
        self.assertEqual(self.config.read_bytes(),
                         self.git_config.replace('ref = "main"', 'ref = "v1.2.3"').encode())
        self.assertEqual(report["hosts"]["claude"], {"path": str(self.claude_copy), "version": "1.2.3"})
        self.assertEqual(report["hosts"]["codex"], {"path": str(self.codex_copy), "version": "1.2.3"})
        self.assertEqual(report["codexConfig"], {"path": str(self.config), "backup": str(self.backup),
                                                 "refChanged": True})
        recorded = json.loads(self.record_path.read_text(encoding="utf-8"))["steps"]["install"]
        self.assertEqual(recorded["status"], "ok")
        self.assertEqual(recorded["hosts"], report["hosts"])
        self.assertRegex(recorded["time"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")
        self.assertIn("publish", json.loads(self.record_path.read_text(encoding="utf-8"))["steps"])

    def test_confirm_fast_forwards_directory_clone_to_tag_before_host_commands(self):
        clone = self.make_clone()
        old_head = self.clone_git(clone, "rev-parse", "HEAD")
        tag_commit = self.fixture.commit({"README.md": "> 状态：1.2.3（接口 2.11）\n安装：--ref v1.2.3\n更多\n"})
        self.fixture.git("push", "-q", "origin", "main")
        self.release_at(tag_commit)
        self.assertNotEqual(old_head, tag_commit)
        report, stdout = self.install()
        self.assertEqual(self.clone_git(clone, "rev-parse", "HEAD"), tag_commit)
        self.assertEqual(self.writes(), ["pull", "claude marketplace update", "claude plugin update",
                                         "codex plugin add"])
        pull = next(call for call in self.fixture.calls() if "pull" in call)
        self.assertEqual(pull, ["git", "-C", str(clone), "pull", "--ff-only"])
        self.assertEqual(report["hosts"]["claude"]["path"], str((clone / "plugins" / "agent-relay").resolve()))

    def test_confirm_refuses_unready_clone_and_leaves_everything_unchanged(self):
        def dirty(clone):
            (clone / "untracked.txt").write_text("local\n", encoding="utf-8")

        def other_branch(clone):
            self.clone_git(clone, "checkout", "-q", "-b", "work")

        def ahead(clone):
            (clone / "local.txt").write_text("local\n", encoding="utf-8")
            self.clone_git(clone, "add", "local.txt")
            self.clone_git(clone, "commit", "-q", "-m", "local only")

        for name, change in (("dirty", dirty), ("other branch", other_branch), ("ahead of tag", ahead)):
            with self.subTest(name=name):
                clone = self.make_clone()
                change(clone)
                before = (self.clone_git(clone, "rev-parse", "HEAD"), self.clone_git(clone, "status", "--porcelain"),
                          self.clone_git(clone, "branch", "--show-current"), self.config.read_bytes())
                self.fixture.calls_log.write_text("", encoding="utf-8")
                self.install(status="refused", reason="clone-not-clean")
                self.assertEqual((self.clone_git(clone, "rev-parse", "HEAD"),
                                  self.clone_git(clone, "status", "--porcelain"),
                                  self.clone_git(clone, "branch", "--show-current"), self.config.read_bytes()),
                                 before)
                self.assertEqual(self.writes(), [])
                self.assertFalse(self.backup.exists())
                self.assertNotIn("install", json.loads(self.record_path.read_text(encoding="utf-8"))["steps"])
                shutil.rmtree(clone)

    def test_confirm_refuses_clone_that_does_not_land_on_the_tag(self):
        clone = self.make_clone()
        tag_commit = self.fixture.commit({"one.txt": "1\n"})
        self.fixture.commit({"two.txt": "2\n"})
        self.fixture.git("push", "-q", "origin", "main")
        self.release_at(tag_commit)
        self.install(status="refused", reason="clone-not-at-tag")
        self.assertEqual(self.writes(), ["pull"])
        self.assertEqual(self.config.read_bytes(), self.git_config.encode())

    def test_confirm_rerun_skips_effects_already_present(self):
        clone = self.make_clone()
        already = self.git_config.replace('ref = "main"', 'ref = "v1.2.3"').encode()
        self.config.write_bytes(already)
        report, stdout = self.install()
        self.assertEqual(self.writes(), ["claude marketplace update", "claude plugin update", "codex plugin add"])
        self.assertFalse(any(call[0] == "git" and "fetch" in call for call in self.fixture.calls()))
        self.assertEqual(self.config.read_bytes(), already)
        self.assertFalse(self.backup.exists())
        self.assertEqual(report["codexConfig"]["refChanged"], False)
        self.assertEqual(self.clone_git(clone, "status", "--porcelain"), "")

    def test_confirm_keeps_local_path_codex_config_and_backs_it_up(self):
        text = '[marketplaces.agent-relay-marketplace]\nsource = "' + str(self.fixture.repo) + '"\n'
        self.config.write_bytes(text.encode())
        self.install()
        self.assertEqual(self.config.read_bytes(), text.encode())
        self.assertEqual(self.backup.read_bytes(), text.encode())

    def test_confirm_fails_naming_a_changed_missing_or_extra_file(self):
        target = "hooks/extra.py"

        def changed(copy):
            (copy / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            return "changed", ".claude-plugin/plugin.json"

        def missing(copy):
            (copy / "bridge" / "src" / "x.ts").unlink()
            return "missing", "bridge/src/x.ts"

        def extra(copy):
            (copy / "hooks").mkdir(exist_ok=True)
            (copy / target).write_text("print()\n", encoding="utf-8")
            return "extra", target

        for host in ("claude", "codex"):
            for change in (changed, missing, extra):
                with self.subTest(host=host, change=change.__name__):
                    self.release_at(self.fixture.head)
                    copy = self.claude_copy if host == "claude" else self.codex_copy
                    kind, name = change(copy)
                    report, stdout = self.install(status="failed", reason="copy-mismatch")
                    self.assertEqual(report["differences"], {host: {kind: [name]}})
                    self.assertIn(name, report["error"])
                    self.assertIn(name, stdout)
                    recorded = json.loads(self.record_path.read_text(encoding="utf-8"))["steps"]["install"]
                    self.assertEqual(recorded["status"], "failed")
                    self.assertEqual(recorded["differences"], report["differences"])

    def test_confirm_fails_when_a_host_copy_cannot_be_found(self):
        self.fixture.answer("codex", ["plugin", "list", "--json"], stdout=json.dumps({"installed": []}))
        shutil.rmtree(self.claude_copy)
        report, stdout = self.install(status="failed", reason="copy-mismatch")
        self.assertEqual(report["differences"], {"claude": {"copy": "not-found"}, "codex": {"copy": "not-found"}})

    def test_confirm_needs_prepared_manifest_before_any_command(self):
        (self.prepared / "MANIFEST.json").unlink()
        before = self.config.read_bytes()
        self.install(status="refused", reason="needs-prepare")
        self.assertEqual(self.fixture.calls(), [])
        self.assertEqual(self.config.read_bytes(), before)

    def test_confirm_refuses_ambiguous_codex_config_before_any_command(self):
        clone = self.make_clone()
        self.fixture.commit({"one.txt": "1\n"})
        self.fixture.git("push", "-q", "origin", "main")
        self.release_at(self.fixture.git("rev-parse", "HEAD"))
        text = self.git_config + '[marketplaces.agent-relay-marketplace]\nref = "x"\n'
        self.config.write_bytes(text.encode())
        head = self.clone_git(clone, "rev-parse", "HEAD")
        self.install(status="refused", reason="codex-ref-ambiguous")
        self.assertEqual(self.writes(), [])
        self.assertEqual(self.clone_git(clone, "rev-parse", "HEAD"), head)
        self.assertEqual(self.config.read_bytes(), text.encode())
        self.assertFalse(self.backup.exists())


class ReleaseUpgradeTests(unittest.TestCase):
    """D283: never stop the bridge; run the installed copy's runtime upgrade only when nothing runs."""

    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)
        self.release = load_release()
        self.record_path = self.fixture.state / "release" / (self.fixture.version + ".json")
        self.copy = self.fixture.root / "claude-copy"
        self.script = self.copy / "hooks" / "native_collaboration_runtime.py"
        self.script.parent.mkdir(parents=True)
        self.script.write_text(FAKE_TOOL, encoding="utf-8")
        self.script.chmod(0o755)
        self.server = str(self.fixture.state / "runtime" / "dist" / "server.js")
        self.command = ["python3", "-B", str(self.script), "upgrade", "--confirm"]
        self.record("check", {"status": "ok", "mergeCommit": self.fixture.head, "runtimeUpgrade": True,
                              "runtimeFiles": ["src/"]})
        self.record("install", {"status": "ok", "hosts": {
            "claude": {"path": str(self.copy), "version": self.fixture.version},
            "codex": {"path": "/elsewhere", "version": self.fixture.version}}})

    def record(self, step, facts):
        with patch.dict(os.environ, self.fixture.env, clear=True):
            self.release.write_record(self.release.read_record(self.fixture.version), step, facts)

    def servers(self, count):
        others = "/usr/bin/other --flag\nnode /some/other/dist/server.js\n"
        self.fixture.answer("ps", ["-axo", "command"],
                            stdout=others + "".join("node " + self.server + "\n" for _ in range(count)))

    def runtime_answer(self, result, returncode=0):
        stdout = result if isinstance(result, str) else json.dumps(result) + "\n"
        self.fixture.answer("native_collaboration_runtime.py", ["upgrade", "--confirm"], stdout=stdout,
                            returncode=returncode)

    def upgrade(self, *args, status="ok", reason=None):
        code, report, stdout = self.fixture.run_release("upgrade", "--version", self.fixture.version, *args)
        self.assertEqual(code, {"ok": 0, "preview": 0, "refused": 2, "waiting-on-user": 3, "failed": 1}[status],
                         stdout)
        self.assertEqual(report["schema"], "agent-relay.release/v1")
        self.assertEqual(report["step"], "upgrade")
        self.assertEqual(report["version"], self.fixture.version)
        self.assertEqual(report["status"], status, stdout)
        if reason:
            self.assertEqual(report["reason"], reason, stdout)
        return report, stdout

    def runtime_calls(self):
        return [call for call in self.fixture.calls() if call[0] == "native_collaboration_runtime.py"]

    def recorded(self):
        return json.loads(self.record_path.read_text(encoding="utf-8"))["steps"].get("upgrade")

    def test_upgrade_skips_when_check_found_no_runtime_change(self):
        self.record("check", {"status": "ok", "mergeCommit": self.fixture.head, "runtimeUpgrade": False,
                              "runtimeFiles": []})
        self.record("install", {"status": "failed"})
        for args in ((), ("--confirm",)):
            with self.subTest(args=args):
                report, stdout = self.upgrade(*args)
                self.assertIs(report["skipped"], True)
                self.assertEqual(self.recorded()["skipped"], True)
        self.assertEqual(self.fixture.calls(), [])

    def test_upgrade_needs_recorded_check_and_install(self):
        cases = (("check", {"status": "refused"}, "needs-check"), ("install", {"status": "failed"}, "needs-install"))
        for step, facts, reason in cases:
            with self.subTest(step=step):
                self.record(step, facts)
                for args in ((), ("--confirm",)):
                    self.upgrade(*args, status="refused", reason=reason)
                self.record("check", {"status": "ok", "mergeCommit": self.fixture.head, "runtimeUpgrade": True})
        self.assertEqual(self.fixture.calls(), [])
        self.assertIsNone(self.recorded())

    def test_upgrade_preview_counts_servers_and_runs_nothing(self):
        self.assertTrue(callable(self.release._runtime._servers_running))
        self.servers(2)
        report, stdout = self.upgrade(status="preview")
        self.assertEqual(report["running"], 2)
        self.assertEqual(report["command"], self.command)
        self.assertEqual(self.fixture.calls(), [["ps", "-axo", "command"]])

    def test_upgrade_confirm_waits_for_user_while_a_bridge_runs(self):
        self.servers(1)
        report, stdout = self.upgrade("--confirm", status="waiting-on-user")
        self.assertEqual(report["running"], 1)
        self.assertIn("ChatGPT", stdout)
        self.assertIn("关闭", stdout)
        self.assertIn("未做任何改动", stdout)
        self.assertEqual(self.runtime_calls(), [])
        self.assertEqual(self.recorded()["status"], "waiting-on-user")

    def test_upgrade_confirm_runs_installed_runtime_once_when_nothing_runs(self):
        for state in ("upgraded", "current"):
            with self.subTest(state=state):
                self.fixture.calls_log.write_text("", encoding="utf-8")
                self.servers(0)
                answer = {"state": state}
                if state == "upgraded":
                    answer.update({"previous": "/runtime.previous-x", "backup": "/backups/x"})
                self.runtime_answer(answer)
                report, stdout = self.upgrade("--confirm")
                self.assertEqual(self.fixture.calls(), [["ps", "-axo", "command"],
                                                        ["native_collaboration_runtime.py", "upgrade", "--confirm"]])
                self.assertEqual(report["state"], state)
                self.assertEqual(report["previous"], answer.get("previous"))
                self.assertEqual(report["backup"], answer.get("backup"))
                self.assertEqual(self.recorded()["status"], "ok")

    def test_upgrade_failure_prints_rollback_and_recover_without_running_them(self):
        outputs = ((json.dumps({"state": "error", "diagnostic": "build failed"}) + "\n", 1),
                   ("not json at all\n", 0), ("", 1))
        for output, returncode in outputs:
            with self.subTest(output=output):
                self.fixture.calls_log.write_text("", encoding="utf-8")
                self.servers(0)
                self.runtime_answer(output, returncode)
                report, stdout = self.upgrade("--confirm", status="failed", reason="runtime-upgrade-failed")
                for command in ("rollback", "recover"):
                    expected = ["python3", "-B", str(self.script), command, "--confirm"]
                    self.assertIn(" ".join(expected), stdout)
                    self.assertIn(expected, report["recovery"])
                self.assertEqual(self.runtime_calls(), [["native_collaboration_runtime.py", "upgrade", "--confirm"]])
                self.assertEqual(self.recorded()["status"], "failed")

    def test_release_command_never_stops_a_process(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("kill(", '"pkill"', '"kill"', "killall", "osascript"):
            self.assertNotIn(forbidden, source)
        self.assertFalse(any("kill" in part for call in self.fixture.calls() for part in call))


class ReleaseSmokeEvidenceBase(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)
        self.release = load_release()
        self.record_path = self.fixture.state / "release" / (self.fixture.version + ".json")
        self.copy = self.fixture.root / "claude-copy"
        self.script = self.copy / "hooks" / "native_collaboration_runtime.py"
        self.script.parent.mkdir(parents=True)
        self.script.write_text(FAKE_TOOL, encoding="utf-8")
        self.script.chmod(0o755)

    def record(self, step, facts):
        with patch.dict(os.environ, self.fixture.env, clear=True):
            self.release.write_record(self.release.read_record(self.fixture.version), step, facts)

    def run_step(self, step, *args, status="ok", reason=None):
        code, report, stdout = self.fixture.run_release(step, "--version", self.fixture.version, *args)
        self.assertEqual(code, {"ok": 0, "refused": 2, "waiting-on-user": 3, "failed": 1}[status], stdout)
        self.assertEqual(report["schema"], "agent-relay.release/v1")
        self.assertEqual(report["step"], step)
        self.assertEqual(report["version"], self.fixture.version)
        self.assertEqual(report["status"], status, stdout)
        if reason:
            self.assertEqual(report["reason"], reason, stdout)
        return report, stdout

    def recorded(self, step):
        if not self.record_path.exists():
            return None
        return json.loads(self.record_path.read_text(encoding="utf-8"))["steps"].get(step)


class ReleaseSmokeTests(ReleaseSmokeEvidenceBase):
    """D284: read-only doctor and status of the installed copy."""

    CHECKS = ("runtime", "claude-plugin", "codex-plugin", "codex-restart")

    def setUp(self):
        super().setUp()
        self.record("check", {"status": "ok", "mergeCommit": self.fixture.head, "runtimeUpgrade": True})
        self.record("install", {"status": "ok", "hosts": {
            "claude": {"path": str(self.copy), "version": self.fixture.version},
            "codex": {"path": "/elsewhere", "version": self.fixture.version}}})
        self.doctor()
        self.status()

    def doctor(self, overrides=None, overall=None, returncode=0, stdout=None):
        states = {name: "ok" for name in self.CHECKS}
        states.update(overrides or {})
        checks = [{"check": name, "state": state, "detail": "d", "next": None} for name, state in states.items()]
        if overall is None:
            overall = "fail" if "fail" in states.values() else "warn" if "warn" in states.values() else "ok"
        if stdout is None:
            stdout = json.dumps({"state": overall, "root": "/runtime", "checks": checks}) + "\n"
        self.fixture.answer("native_collaboration_runtime.py", ["doctor"], stdout=stdout, returncode=returncode)

    def status(self, current=True):
        self.fixture.answer("native_collaboration_runtime.py", ["status"],
                            stdout=json.dumps({"state": "ready", "bridge": {"current": current}}) + "\n")

    def test_smoke_needs_recorded_install(self):
        self.record("install", {"status": "failed"})
        self.run_step("smoke", status="refused", reason="needs-install")
        self.assertEqual(self.fixture.calls(), [])

    def test_smoke_all_ok_lists_every_check_and_runs_only_read_commands(self):
        report, stdout = self.run_step("smoke")
        self.assertEqual(report["checks"], [{"name": name, "state": "ok"} for name in self.CHECKS])
        self.assertEqual(self.fixture.calls(), [["native_collaboration_runtime.py", "doctor"],
                                                ["native_collaboration_runtime.py", "status"]])
        self.assertEqual(self.recorded("smoke")["status"], "ok")

    def test_smoke_doctor_fail_is_failed(self):
        self.doctor({"runtime": "fail", "codex-restart": "warn"}, returncode=1)
        report, stdout = self.run_step("smoke", status="failed", reason="doctor-fail")
        self.assertIn({"name": "runtime", "state": "fail"}, report["checks"])
        self.assertEqual(self.recorded("smoke")["status"], "failed")

    def test_smoke_unreadable_doctor_output_is_failed(self):
        self.doctor(stdout="Traceback: boom\n", returncode=1)
        self.run_step("smoke", status="failed", reason="doctor-unreadable")

    def test_smoke_codex_restart_warn_waits_for_user(self):
        self.doctor({"codex-restart": "warn"})
        report, stdout = self.run_step("smoke", status="waiting-on-user")
        self.assertEqual(report["waiting"], ["codex-restart"])
        self.assertIn("ChatGPT", stdout)
        self.assertEqual(self.recorded("smoke")["status"], "waiting-on-user")

    def test_smoke_claude_plugin_not_ok_waits_for_user(self):
        for state in ("warn", "skip"):
            with self.subTest(state=state):
                self.doctor({"claude-plugin": state})
                report, stdout = self.run_step("smoke", status="waiting-on-user")
                self.assertEqual(report["waiting"], ["claude-plugin"])
                self.assertIn("Claude Code", stdout)

    def test_smoke_bridge_not_current_waits_only_when_upgrade_was_needed(self):
        self.status(current=False)
        report, stdout = self.run_step("smoke", status="waiting-on-user")
        self.assertEqual(report["waiting"], ["runtime-upgrade"])
        self.assertIn("upgrade", stdout)
        self.record("check", {"status": "ok", "mergeCommit": self.fixture.head, "runtimeUpgrade": False})
        self.run_step("smoke")


class ReleaseEvidenceTests(ReleaseSmokeEvidenceBase):
    """D285: a Markdown summary of the local record, never written into the repo."""

    def full_record(self):
        self.record("check", {"status": "ok", "mergeCommit": self.fixture.head, "previousTag": "v1.2.2",
                              "interface": {"from": "2.10", "to": "2.11"}, "runtimeUpgrade": True,
                              "runtimeFiles": ["src/"]})
        self.record("prepare", {"status": "ok", "dir": "/prepared", "manifestSha256": "abc", "files": 7})
        self.record("publish", {"status": "ok", "tag": "v1.2.3", "releaseUrl": "https://example.invalid/r/v1.2.3",
                                "peeledCommit": self.fixture.head})
        self.record("install", {"status": "ok", "hosts": {
            "claude": {"path": "/claude-copy", "version": "1.2.3"},
            "codex": {"path": "/codex-copy", "version": "1.2.3"}}, "time": "2026-11-23T00:00:00+00:00"})
        self.record("upgrade", {"status": "ok", "state": "upgraded", "previous": "/runtime.previous-x",
                                "backup": "/backups/x"})
        self.record("smoke", {"status": "waiting-on-user", "waiting": ["codex-restart"],
                              "message": "请用 ⌘Q 退出 ChatGPT 后重新打开。",
                              "checks": [{"name": "runtime", "state": "ok"}, {"name": "codex-restart",
                                                                               "state": "warn"}]})

    def test_evidence_with_only_check_names_the_missing_steps(self):
        self.record("check", {"status": "ok", "mergeCommit": self.fixture.head, "previousTag": None,
                              "interface": {"from": None, "to": "2.11"}, "runtimeUpgrade": True,
                              "runtimeFiles": []})
        report, stdout = self.run_step("evidence")
        self.assertEqual(report["missing"], ["prepare", "publish", "install", "upgrade", "smoke"])
        self.assertIn(self.fixture.head, stdout)
        for step in report["missing"]:
            self.assertIn(step, stdout)
        self.assertEqual(self.fixture.calls(), [])
        self.assertEqual(self.fixture.git("status", "--porcelain"), "")

    def test_evidence_without_any_record_is_ok(self):
        report, stdout = self.run_step("evidence")
        self.assertEqual(report["missing"], ["check", "prepare", "publish", "install", "upgrade", "smoke"])
        self.assertFalse(self.record_path.exists())

    def test_evidence_summarises_every_recorded_step(self):
        self.full_record()
        before = self.record_path.read_bytes()
        report, stdout = self.run_step("evidence")
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["waiting"], ["smoke: codex-restart"])
        for text in (self.fixture.head, "v1.2.3", "https://example.invalid/r/v1.2.3", "v1.2.2", "2.10", "2.11",
                     "src/", "/claude-copy", "/codex-copy", "upgraded", "/backups/x", "codex-restart", "ChatGPT"):
            self.assertIn(text, stdout)
        self.assertEqual(self.record_path.read_bytes(), before)

    def test_evidence_output_inside_repo_is_refused(self):
        self.full_record()
        for target in (self.fixture.repo / "evidence.md", self.fixture.root / "outside" / ".." / "repo" / "e.md"):
            with self.subTest(target=target):
                self.run_step("evidence", "--output", str(target), status="refused", reason="output-in-repo")
                self.assertFalse((self.fixture.repo / target.name).exists())
        self.assertEqual(self.fixture.git("status", "--porcelain"), "")

    def test_evidence_output_outside_repo_is_written(self):
        self.full_record()
        target = self.fixture.root / "evidence.md"
        report, stdout = self.run_step("evidence", "--output", str(target))
        self.assertEqual(report["output"], str(target.resolve()))
        text = target.read_text(encoding="utf-8")
        self.assertIn("v1.2.3", text)
        self.assertIn("/claude-copy", text)

if __name__ == "__main__":
    unittest.main()
