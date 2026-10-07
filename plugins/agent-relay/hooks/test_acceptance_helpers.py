#!/usr/bin/env python3
"""Acceptance helpers: preflight is read-only and complete; cleanup touches only one run's identities."""
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PREFLIGHT = REPO / "scripts" / "acceptance" / "preflight.sh"
CLEANUP = REPO / "scripts" / "acceptance" / "cleanup.sh"


class PreflightFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-preflight-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.claude_home = self.tmp / "claude"
        (self.claude_home / "plugins").mkdir(parents=True)
        self.codex_home = self.tmp / "codex"
        self.codex_home.mkdir()

    def fake(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        path.chmod(0o755)

    def run_preflight(self):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.claude_home), CODEX_HOME=str(self.codex_home),
                   HOME=str(self.tmp), PATH=f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin")
        done = subprocess.run(["/bin/bash", str(PREFLIGHT)], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout


class PreflightTests(PreflightFixture):
    def test_reports_versions_installs_reviewer_and_launch_command(self):
        self.fake("claude", 'echo "9.9.9 (Claude Code)"')
        listing = {"installed": [{"pluginId": "agent-relay@relay", "name": "agent-relay", "version": "0.1.0",
                                  "enabled": True, "source": {"path": "/x/agent-relay"}}]}
        (self.tmp / "codex.json").write_text(json.dumps(listing), encoding="utf-8")
        self.fake("codex", f'case "$1" in --version) echo "codex-cli 9.0";; *) cat "{self.tmp}/codex.json";; esac')
        (self.claude_home / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"version": 2, "plugins": {"agent-relay@relay": [{"installPath": "/y/agent-relay", "version": "0.1.0",
                                                                "gitCommitSha": "abc123"}]}}), encoding="utf-8")
        (self.codex_home / "config.toml").write_text('approvals_reviewer = "guardian_subagent"\n', encoding="utf-8")
        before = sorted((p, p.stat().st_mtime_ns) for p in self.tmp.rglob("*"))
        out = self.run_preflight()
        self.assertEqual(before, sorted((p, p.stat().st_mtime_ns) for p in self.tmp.rglob("*")))
        self.assertIn("9.9.9 (Claude Code)", out)
        self.assertIn("codex-cli 9.0", out)
        self.assertIn("agent-relay@relay 0.1.0 abc123 /y/agent-relay", out)
        self.assertIn("agent-relay@relay 0.1.0 enabled=True /x/agent-relay", out)
        self.assertIn("guardian_subagent  <- counts as auto-approval", out)
        launch = next(line for line in out.splitlines() if line.startswith("claude test session"))
        self.assertIn("--permission-mode dontAsk", launch)
        self.assertNotIn('--tools ""', launch)
        for tool in ("ListAgents", "SendMessage", "__bridge_register", "__bridge_wait"):
            self.assertIn(tool, launch)

    def test_missing_hosts_and_plugin_are_reported_not_fatal(self):
        out = self.run_preflight()
        self.assertIn("claude version        unavailable", out)
        self.assertIn("agent-relay (Claude)  not installed", out)
        self.assertIn("agent-relay (Codex)   unknown", out)
        self.assertIn("codex approvals       no config.toml", out)


def load_preflight():
    import importlib.util
    spec = importlib.util.spec_from_file_location("preflight", REPO / "scripts" / "acceptance" / "preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StaleCopyTests(PreflightFixture):
    """acceptance-kit-round2 D54 (round 2 R2-5, R2-11): every copy a host runs is compared with this checkout."""

    def copy_source(self, target):
        shutil.copytree(REPO / "plugins" / "agent-relay", target,
                        ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".DS_Store"))
        return target

    def test_tree_hash_sees_content_and_ignores_host_and_build_entries(self):
        preflight = load_preflight()
        a = self.copy_source(self.tmp / "a")
        b = self.copy_source(self.tmp / "b")
        self.assertEqual(preflight.tree_hash(a), preflight.tree_hash(b))
        for ignored in ("node_modules/x.js", "migrated-command-skills/s.md", "hooks/__pycache__/x.pyc", ".git/HEAD"):
            (b / ignored).parent.mkdir(parents=True, exist_ok=True)
            (b / ignored).write_text("host or build output", encoding="utf-8")
        self.assertEqual(preflight.tree_hash(a), preflight.tree_hash(b))
        (b / "skills" / "collab" / "SKILL.md").write_text("changed", encoding="utf-8")
        self.assertNotEqual(preflight.tree_hash(a), preflight.tree_hash(b))
        self.assertIsNone(preflight.tree_hash(self.tmp / "missing"))

    def test_marks_the_copy_each_host_runs_current_or_stale(self):
        market = self.tmp / "market"
        self.copy_source(market / "plugins" / "agent-relay")
        (market / ".claude-plugin").mkdir(parents=True)
        (market / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
            {"name": "relay", "plugins": [{"name": "agent-relay", "source": "./plugins/agent-relay"}]}), encoding="utf-8")
        (self.claude_home / "plugins" / "known_marketplaces.json").write_text(json.dumps(
            {"relay": {"source": {"source": "directory", "path": str(market)}, "installLocation": str(market)}}),
            encoding="utf-8")
        cache = self.claude_home / "plugins" / "cache" / "relay" / "agent-relay" / "0.1.0"
        cache.mkdir(parents=True)
        (self.claude_home / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"version": 2, "plugins": {"agent-relay@relay": [{"installPath": str(cache), "version": "0.1.0",
                                                                "gitCommitSha": "old"}]}}), encoding="utf-8")
        codex_cache = self.copy_source(self.codex_home / "plugins" / "cache" / "relay" / "agent-relay" / "0.1.0")
        (codex_cache / "migrated-command-skills").mkdir()
        (codex_cache / "hooks" / "session_routing.py").write_text("# round-1 era copy\n", encoding="utf-8")
        listing = {"installed": [{"pluginId": "agent-relay@relay", "name": "agent-relay", "version": "0.1.0",
                                  "enabled": True, "source": {"path": str(market / "plugins" / "agent-relay")}}]}
        (self.tmp / "codex.json").write_text(json.dumps(listing), encoding="utf-8")
        self.fake("codex", f'case "$1" in --version) echo "codex-cli 9.0";; *) cat "{self.tmp}/codex.json";; esac')
        before = sorted((p, p.stat().st_mtime_ns) for p in self.tmp.rglob("*"))
        out = self.run_preflight()
        self.assertEqual(before, sorted((p, p.stat().st_mtime_ns) for p in self.tmp.rglob("*")), "read only")
        lines = out.splitlines()
        loaded = next(line for line in lines if str(market / "plugins" / "agent-relay") in line and "Claude" in line)
        self.assertIn("current", loaded)
        record = next(line for line in lines if str(cache) in line)
        self.assertIn("not loaded", record)
        self.assertNotIn("STALE", record)
        stale = next(line for line in lines if str(codex_cache) in line)
        self.assertIn("STALE", stale)
        self.assertIn("codex plugin add agent-relay@relay", stale)


class CleanupTests(unittest.TestCase):
    """Run a copy of cleanup.sh in a fake repository whose retire entry only logs its arguments."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-cleanup-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        hooks = self.tmp / "repo" / "plugins" / "agent-relay" / "hooks"
        hooks.mkdir(parents=True)
        (self.tmp / "repo" / "scripts" / "acceptance").mkdir(parents=True)
        shutil.copy(CLEANUP, self.tmp / "repo" / "scripts" / "acceptance" / "cleanup.sh")
        self.log = self.tmp / "retired.log"
        (hooks / "native_collaboration_runtime.py").write_text(
            "from pathlib import Path\nclass StateHomeError(ValueError):\n    pass\n"
            f"def default_root():\n    return Path({str(self.tmp / 'root')!r})\n",
            encoding="utf-8")
        (hooks / "native_collaboration_retire.py").write_text(
            "import sys\n"
            f"open({str(self.log)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
            "print('{\"state\": \"retired\"}')\n", encoding="utf-8")
        mailbox = self.tmp / "root" / "mailbox"
        mailbox.mkdir(parents=True)
        self.database = mailbox / "bridge.sqlite"
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE agents (name TEXT PRIMARY KEY, capabilities TEXT NOT NULL, "
                               "registered_at TEXT NOT NULL, last_seen TEXT NOT NULL, retired_at TEXT, "
                               "retired_by TEXT, retire_note TEXT)")
            for name, retired in (("ar-acc-r1-a-claude", None), ("ar-acc-r1-b-codex", None),
                                  ("ar-acc-r1-c-codex", "2026-10-07"), ("ar-acc-r10-x-claude", None),
                                  ("sg-baseline-A-claude", None)):
                connection.execute("INSERT INTO agents VALUES (?, '[]', 't', 't', ?, NULL, NULL)", (name, retired))

    def run_cleanup(self, *args):
        return subprocess.run(["/bin/bash", str(self.tmp / "repo" / "scripts" / "acceptance" / "cleanup.sh"),
                               *args], capture_output=True, text=True, timeout=60)

    def test_preview_lists_only_live_identities_of_this_run_and_retires_nothing(self):
        before = self.database.read_bytes()
        done = self.run_cleanup("r1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("ar-acc-r1-a-claude", done.stdout)
        self.assertIn("ar-acc-r1-b-codex", done.stdout)
        for other in ("ar-acc-r1-c-codex", "ar-acc-r10-x-claude", "sg-baseline-A-claude"):
            self.assertNotIn(other, done.stdout)
        self.assertIn("preview only", done.stdout)
        self.assertFalse(self.log.exists())
        self.assertEqual(before, self.database.read_bytes())

    def test_confirm_retires_exactly_those_names_one_at_a_time(self):
        done = self.run_cleanup("r1", "--confirm")
        self.assertEqual(done.returncode, 0, done.stderr)
        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual([call.split()[1] for call in calls], ["ar-acc-r1-a-claude", "ar-acc-r1-b-codex"])
        self.assertTrue(all("--confirm-retire" in call for call in calls))

    def test_rejects_a_run_id_that_could_widen_the_prefix(self):
        for run in ("", "R1", "r1*", "../r1"):
            with self.subTest(run=run):
                self.assertNotEqual(self.run_cleanup(run).returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
