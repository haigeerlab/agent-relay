"""Every host config write keeps a private copy first (safe-uninstall assumption 3)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from host_backup import HostBackupError, backup_host_files
from native_collaboration_adapters import codex_fragment, main
from native_collaboration_runtime import BRIDGE_COMMIT

SECRET = "ctx7sk-not-a-real-key"


class HostBackupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-backup-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.home = self.base / "relay"
        self.codex = self.base / "codex" / "config.toml"
        self.codex.parent.mkdir()
        self.codex.write_text('approval_policy = "on-request"\n')
        self.claude_json = self.base / ".claude.json"
        self.claude_json.write_text(json.dumps({"mcpServers": {"context7": {"headers": {"KEY": SECRET}}}}))
        old = os.umask(0o002)
        self.addCleanup(os.umask, old)

    def mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)

    def test_copies_are_private_whatever_the_umask_and_missing_files_are_recorded(self):
        missing = self.base / "nope" / "settings.json"
        (self.home / "backups").mkdir(parents=True)
        for directory in (self.home, self.home / "backups"):
            directory.chmod(0o755)  # pre-existing and too open: tightened, not trusted
        with patch.dict(os.environ, {"AGENT_RELAY_HOME": str(self.home)}):
            target = backup_host_files([self.codex, self.claude_json, missing])
        self.assertEqual(target.parent.parent.parent, self.home)
        self.assertEqual(target.name, "host-config")
        for directory in (target, target.parent, target.parent.parent):
            self.assertEqual(self.mode(directory), 0o700, directory)
        self.assertEqual((target / "config.toml").read_bytes(), self.codex.read_bytes())
        self.assertEqual((target / ".claude.json").read_bytes(), self.claude_json.read_bytes())
        for copy in target.iterdir():
            self.assertEqual(self.mode(copy), 0o600, copy)
        self.assertEqual((target / "missing.txt").read_text(), str(missing) + "\n")

    def test_two_backups_in_one_second_do_not_overwrite_each_other(self):
        with patch.dict(os.environ, {"AGENT_RELAY_HOME": str(self.home)}):
            first = backup_host_files([self.codex])
            second = backup_host_files([self.codex])
        self.assertNotEqual(first, second)

    def test_a_failed_copy_raises_and_a_symlink_is_refused(self):
        blocked = self.base / "blocked"
        blocked.write_text("not a directory")
        with patch.dict(os.environ, {"AGENT_RELAY_HOME": str(blocked)}), self.assertRaises(HostBackupError):
            backup_host_files([self.codex])
        link = self.base / "link.toml"
        link.symlink_to(self.codex)
        with patch.dict(os.environ, {"AGENT_RELAY_HOME": str(self.home)}), self.assertRaises(HostBackupError):
            backup_host_files([link])


class AdapterBackupTests(unittest.TestCase):
    """install-codex / uninstall-codex / install-claude / uninstall-claude each back up before writing."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-adapter-backup-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.relay = self.base / "relay"
        self.root = self.relay / "runtime"
        for sub in ("mailbox/backups", "data", "dist"):
            (self.root / sub).mkdir(parents=True, mode=0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        for directory in (self.root, self.root / "mailbox", self.root / "mailbox" / "backups", self.root / "data"):
            directory.chmod(0o700)
        self.node = self.base / "node"
        self.node.write_text("#!/bin/sh\n")
        self.node.chmod(0o755)
        self.codex = self.base / "config.toml"
        self.codex.write_text('model = "x"\n')
        self.settings = self.base / "settings.json"
        self.settings.write_text(json.dumps({"permissions": {"deny": ["Bash(rm:*)"]}}))
        self.claude_json = self.base / ".claude.json"
        self.claude_json.write_text(json.dumps({"mcpServers": {"context7": {"headers": {"KEY": SECRET}}}}))
        self.claude = self.base / "claude"
        self.claude.write_text("#!/bin/sh\nexit 0\n")
        self.claude.chmod(0o755)
        self.sessions = self.base / "claude-sessions"
        self.sessions.mkdir()

    def run_main(self, command, *, relay=None):
        out = io.StringIO()
        argv = [command, "--root", str(self.root), "--node", str(self.node), "--codex-config", str(self.codex),
                "--claude-settings", str(self.settings), "--claude-json", str(self.claude_json),
                "--claude-bin", str(self.claude), "--claude-sessions", str(self.sessions), "--confirm-uninstall"]
        with patch.dict(os.environ, {"AGENT_RELAY_HOME": str(relay or self.relay)}), contextlib.redirect_stdout(out):
            try:
                code = main(argv)
            except SystemExit as error:
                code = error.code
        return code, out.getvalue()

    def backups(self):
        root = self.relay / "backups"
        return sorted(root.glob("*/host-config")) if root.exists() else []

    def test_each_write_backs_up_the_files_it_touches_and_says_they_may_hold_credentials(self):
        expected = {
            "install-codex": {"config.toml"},
            "uninstall-codex": {"config.toml"},
            "install-claude": {"settings.json", ".claude.json"},
            "uninstall-claude": {"settings.json", ".claude.json"},
        }
        for command, names in expected.items():
            with self.subTest(command=command):
                before = len(self.backups())
                code, output = self.run_main(command)
                self.assertEqual(code, 0, output)
                self.assertEqual(len(self.backups()), before + 1)
                latest = self.backups()[-1]
                self.assertEqual({path.name for path in latest.iterdir()}, names)
                self.assertIn(str(latest), output)
                self.assertIn("credentials", output)
                self.assertNotIn(SECRET, output)

    def test_no_write_when_the_backup_fails(self):
        blocked = self.base / "blocked"
        blocked.write_text("not a directory")
        before = self.codex.read_bytes()
        code, output = self.run_main("install-codex", relay=blocked)
        self.assertNotEqual(code, 0)
        self.assertEqual(self.codex.read_bytes(), before)
        self.assertNotIn(codex_fragment(self.root, self.node), self.codex.read_text())


    def test_uninstall_claude_removes_exactly_the_agent_relay_deny_rules(self):
        self.assertEqual(self.run_main("install-claude")[0], 0)
        settings = json.loads(self.settings.read_text())
        settings["permissions"]["allow"] = ["Read"]
        settings["theme"] = "dark"
        self.settings.write_text(json.dumps(settings))
        self.settings.chmod(0o640)
        code, output = self.run_main("uninstall-claude")
        self.assertEqual(code, 0, output)
        after = json.loads(self.settings.read_text())
        self.assertEqual(after["permissions"]["deny"], ["Bash(rm:*)"])
        self.assertEqual(after["permissions"]["allow"], ["Read"])
        self.assertEqual(after["theme"], "dark")
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o640)
        self.assertIn("7 deny rules removed", output)
        before = self.settings.read_bytes()
        code, output = self.run_main("uninstall-claude")
        self.assertIn("no deny rules to remove", output)
        self.assertEqual(self.settings.read_bytes(), before, "nothing to remove, nothing written")

    def test_uninstall_claude_keeps_the_deny_rules_while_a_claude_session_is_open(self):
        # round2-fixes D52 (round 2 R2-10): with every bridge stopped, an open session still re-filtered its cached
        # tool list against the new settings and offered the upstream worker tools once the rules were gone.
        self.assertEqual(self.run_main("install-claude")[0], 0)
        (self.sessions / f"{os.getpid()}.json").write_text(json.dumps({"pid": os.getpid(), "sessionId": "s-open"}))
        with patch("native_collaboration_adapters._servers_running", return_value=0):
            code, output = self.run_main("uninstall-claude")
        self.assertEqual(code, 0, output)
        deny = json.loads(self.settings.read_text())["permissions"]["deny"]
        self.assertEqual(len([rule for rule in deny if rule.startswith("mcp__agent-relay__")]), 7)
        self.assertIn("deny rules kept", output)
        self.assertIn("1 Claude Code session", output)
        self.assertIn("close every Claude Code session", output)
        self.assertIn("uninstall-claude --confirm-uninstall", output)
        self.assertIn(f"--claude-settings {self.settings}", output)
        (self.sessions / f"{os.getpid()}.json").unlink()
        with patch("native_collaboration_adapters._servers_running", return_value=0):
            code, output = self.run_main("uninstall-claude")
        self.assertIn("7 deny rules removed", output)

    def test_uninstall_claude_keeps_the_deny_rules_while_a_bridge_runs_or_cannot_be_checked(self):
        from native_collaboration_runtime import NativeRuntimeError

        self.assertEqual(self.run_main("install-claude")[0], 0)
        for counter in ({"return_value": 2}, {"side_effect": NativeRuntimeError("cannot list processes")}):
            with self.subTest(counter=counter), patch("native_collaboration_adapters._servers_running", **counter):
                code, output = self.run_main("uninstall-claude")
                self.assertEqual(code, 0, output)
                self.assertIn("deny rules kept", output)
        deny = json.loads(self.settings.read_text())["permissions"]["deny"]
        self.assertEqual(len([rule for rule in deny if rule.startswith("mcp__agent-relay__")]), 7)
        self.assertIn("Native Claude MCP entry", output)


if __name__ == "__main__":
    unittest.main()
