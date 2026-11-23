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

    def test_remaining_subcommands_are_placeholders(self):
        for step in ("publish", "install", "upgrade", "smoke", "evidence"):
            with self.subTest(step=step):
                args = ["--version", self.fixture.version]
                args += ["--repo", str(self.fixture.repo), "--remote", "origin", "--github", "example/agent-relay"]
                if step in ("publish", "install", "upgrade"):
                    args.append("--confirm")
                if step == "evidence":
                    args += ["--output", str(self.fixture.root / "evidence.md")]
                report = self.assert_report(self.fixture.run_release(step, *args), step,
                                            self.fixture.version, "refused", 2)
                self.assertEqual(report["reason"], "not-implemented")
        self.assertEqual(self.fixture.calls(), [])
        self.assertEqual(list(self.fixture.state.iterdir()), [])

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


if __name__ == "__main__":
    unittest.main()
