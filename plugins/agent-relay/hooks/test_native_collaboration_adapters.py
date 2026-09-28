"""Native bridge host fragments stay narrow and do not edit real user settings."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_collaboration_adapters import (CODEX_SERVER_NAME, DENIED_TOOLS,
                                           claude_config,
                                           codex_fragment, install_claude_config,
                                           install_codex_config)
from native_collaboration_runtime import BRIDGE_COMMIT


class NativeCollaborationAdaptersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sg-native-adapters-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "native"
        self.root.mkdir(mode=0o700)
        (self.root / "mailbox").mkdir(mode=0o700)
        (self.root / "mailbox" / "backups").mkdir(mode=0o700)
        (self.root / "data").mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        self.node = Path(self.tmp.name) / "node"
        self.node.write_text("node\n")
        self.node.chmod(0o755)

    def test_codex_fragment_is_mailbox_only_and_no_secret(self):
        fragment = codex_fragment(self.root, self.node)
        self.assertIn(f"[mcp_servers.{CODEX_SERVER_NAME}]", fragment)
        self.assertIn(f"command = {json.dumps(str(self.node.resolve()))}", fragment)
        self.assertIn(f"args = {json.dumps([str(self.root / 'dist' / 'server.js')])}", fragment)
        self.assertIn(f"BRIDGE_DB_PATH = {json.dumps(str(self.root / 'mailbox' / 'bridge.sqlite'))}",
                      fragment)
        self.assertIn(f"XDG_DATA_HOME = {json.dumps(str(self.root / 'data'))}", fragment)
        self.assertIn("enabled_tools = " + json.dumps([
            "bridge_register", "bridge_send", "bridge_inbox", "bridge_ack", "bridge_outbox",
            "bridge_agents", "bridge_sessions", "bridge_wake_status", "bridge_thread",
            "bridge_wait"]), fragment)
        self.assertNotIn("ask_codex", fragment)
        self.assertNotIn("token", fragment.lower())

    def test_claude_fragment_and_exact_deny_rules_leave_chrome_alone(self):
        result = claude_config(self.root, self.node)
        server = result["mcpServers"]["spec-guard-native-collaboration"]
        self.assertEqual(server["command"], str(self.node.resolve()))
        self.assertEqual(server["env"]["BRIDGE_DB_PATH"],
                         str(self.root / "mailbox" / "bridge.sqlite"))
        self.assertEqual(server["env"]["XDG_DATA_HOME"], str(self.root / "data"))
        # 逐字写死期望的拒绝清单，不能用被测常量的长度去验证它自己。
        self.assertEqual(sorted(result["denyRules"]), sorted(
            "mcp__spec-guard-native-collaboration__" + tool for tool in (
                "bridge_retire", "ask_codex", "review_with_codex", "bridge_orchestrate_codex",
                "bridge_continue_codex", "bridge_orchestration_wait",
                "bridge_orchestration_status")))
        self.assertTrue(all(rule.startswith("mcp__spec-guard-native-collaboration__")
                            for rule in result["denyRules"]))
        self.assertNotIn("chrome", json.dumps(result).lower())
        self.assertNotIn("token", json.dumps(result).lower())

    def test_both_fragments_refuse_absent_runtime(self):
        absent = self.root / "missing"
        with self.assertRaisesRegex(ValueError, "not ready"):
            codex_fragment(absent, self.node)
        with self.assertRaisesRegex(ValueError, "not ready"):
            claude_config(absent, self.node)

    def test_codex_install_appends_without_touching_chrome_or_existing_servers(self):
        target = Path(self.tmp.name) / "config.toml"
        original = '[mcp_servers.chrome]\ncommand = "chrome"\n\n[mcp_servers.spec_guard_collaboration]\nurl = "http://127.0.0.1:9100/mcp"\n'
        target.write_text(original)
        install_codex_config(self.root, self.node, target)
        self.assertTrue(target.read_text().startswith(original))
        self.assertIn(f"[mcp_servers.{CODEX_SERVER_NAME}]", target.read_text())
        with self.assertRaisesRegex(ValueError, "already exists"):
            install_codex_config(self.root, self.node, target)

    def test_claude_install_denies_worker_tools_before_adding_server(self):
        target = Path(self.tmp.name) / "settings.json"
        original = {"chrome": {"enabled": True}, "permissions": {"deny": ["existing-rule"]}}
        target.write_text(json.dumps(original))
        calls = []

        def fake_run(command, **_kwargs):
            calls.append(command)
            if command[2] == "get":
                return subprocess.CompletedProcess(command, 1, "No MCP server named", "")
            settings = json.loads(target.read_text())
            self.assertEqual(settings["chrome"], original["chrome"])
            self.assertEqual(settings["permissions"]["deny"][0], "existing-rule")
            self.assertEqual(len(settings["permissions"]["deny"]), 1 + len(DENIED_TOOLS))
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("native_collaboration_adapters.subprocess.run", side_effect=fake_run):
            install_claude_config(self.root, self.node, target, "claude")
        self.assertEqual(calls[1][:3], ["claude", "mcp", "add-json"])
        self.assertEqual(calls[1][-2:], ["--scope", "user"])
        self.assertEqual(json.loads(target.read_text())["chrome"], original["chrome"])

    def test_claude_install_refuses_unknown_existing_server(self):
        target = Path(self.tmp.name) / "settings.json"
        target.write_text('{"permissions":{"deny":[]}}')
        with patch("native_collaboration_adapters.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, "exists", "")):
            with self.assertRaisesRegex(ValueError, "already exists"):
                install_claude_config(self.root, self.node, target, "claude")
        self.assertEqual(target.read_text(), '{"permissions":{"deny":[]}}')

    def test_claude_registration_failure_keeps_deny_rules(self):
        target = Path(self.tmp.name) / "settings.json"
        target.write_text('{"chrome":{"enabled":true}}')

        def fake_run(command, **_kwargs):
            if command[2] == "get":
                return subprocess.CompletedProcess(command, 1, "No MCP server named", "")
            return subprocess.CompletedProcess(command, 1, "", "registration failed")

        with patch("native_collaboration_adapters.subprocess.run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "deny rules are installed"):
                install_claude_config(self.root, self.node, target, "claude")
        saved = json.loads(target.read_text())
        self.assertEqual(saved["chrome"], {"enabled": True})
        self.assertEqual(len(saved["permissions"]["deny"]), len(DENIED_TOOLS))

    def test_codex_install_refuses_symlinked_config(self):
        actual = Path(self.tmp.name) / "actual.toml"
        actual.write_text('model = "keep"\n')
        linked = Path(self.tmp.name) / "linked.toml"
        linked.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, "not a symlink"):
            install_codex_config(self.root, self.node, linked)
        self.assertEqual(actual.read_text(), 'model = "keep"\n')


if __name__ == "__main__":
    unittest.main()
