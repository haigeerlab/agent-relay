#!/usr/bin/env python3
"""Release commands: isolated repositories, fake host tools and the D278/D286 contract."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "release.py"


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
        return subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, "-C", str(self.repo), *args],
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

    def test_all_seven_subcommands_are_placeholders(self):
        for step in ("check", "prepare", "publish", "install", "upgrade", "smoke", "evidence"):
            with self.subTest(step=step):
                args = ["--pr", "7"] if step == "check" else ["--version", self.fixture.version]
                args += ["--repo", str(self.fixture.repo), "--remote", "origin", "--github", "example/agent-relay"]
                if step in ("publish", "install", "upgrade"):
                    args.append("--confirm")
                if step == "evidence":
                    args += ["--output", str(self.fixture.root / "evidence.md")]
                report = self.assert_report(self.fixture.run_release(step, *args), step,
                                            None if step == "check" else self.fixture.version, "refused", 2)
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


if __name__ == "__main__":
    unittest.main()
