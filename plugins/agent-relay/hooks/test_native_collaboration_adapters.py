"""Native bridge host fragments stay narrow and do not edit real user settings."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_collaboration_adapters import (CODEX_SERVER_NAME,
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

    def test_claude_allow_rules_print_the_exact_rules_and_write_nothing(self):
        # mailbox-polish D156: one-time approval lines for Claude, printed only; the user decides to add them.
        import contextlib
        import io
        from native_collaboration_adapters import main
        from native_collaboration_runtime import MAILBOX_TOOLS
        settings = Path(self.tmp.name) / "never" / "settings.json"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["claude-allow-rules", "--claude-settings", str(settings)]), 0)
        text = out.getvalue()
        expected = ["mcp__agent-relay__" + tool for tool in MAILBOX_TOOLS]
        self.assertEqual(len(expected), 10)
        for rule in expected:
            self.assertEqual(text.count('"%s"' % rule), 1, rule)
        self.assertNotIn("*", text)
        snippet = json.loads(text[text.index("{"):])
        self.assertEqual(snippet, {"permissions": {"allow": expected}})
        self.assertIn("~/.claude/settings.json", text)
        self.assertFalse(settings.exists())
        self.assertFalse(settings.parent.exists())

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

    def test_claude_fragment_has_no_deny_rules_and_leaves_chrome_alone(self):
        result = claude_config(self.root, self.node)
        server = result["mcpServers"]["agent-relay"]
        self.assertEqual(server["command"], str(self.node.resolve()))
        self.assertEqual(server["env"]["BRIDGE_DB_PATH"],
                         str(self.root / "mailbox" / "bridge.sqlite"))
        self.assertEqual(server["env"]["XDG_DATA_HOME"], str(self.root / "data"))
        # orchestrator-removal D92: the server no longer has worker tools, so there is nothing to deny.
        self.assertNotIn("denyRules", result)
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

    def test_claude_install_adds_the_server_and_leaves_the_settings_alone(self):
        target = Path(self.tmp.name) / "settings.json"
        original = {"chrome": {"enabled": True}, "permissions": {"deny": ["existing-rule"]}}
        target.write_text(json.dumps(original))
        before = target.read_bytes()
        calls = []

        def fake_run(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("host_config_removal.subprocess.run", side_effect=fake_run):
            install_claude_config(self.root, self.node, target, "claude")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:3], ["claude", "mcp", "add-json"])
        self.assertEqual(calls[0][-2:], ["--scope", "user"])
        self.assertEqual(target.read_bytes(), before, "orchestrator-removal D92: no deny rules are written")
        absent = Path(self.tmp.name) / "absent-settings.json"
        with patch("host_config_removal.subprocess.run", side_effect=fake_run):
            install_claude_config(self.root, self.node, absent, "claude")
        self.assertFalse(absent.exists(), "a missing settings file is not created")

    def test_claude_install_refuses_an_existing_server_and_leaves_the_settings_alone(self):
        target = Path(self.tmp.name) / "settings.json"
        target.write_text('{"permissions":{"deny":[]}}')
        # 真实 CLI（2026-09-28 实测）：同名时 rc=1，输出 "MCP server X already exists in user config"。
        with patch("host_config_removal.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 1, "", "MCP server agent-relay already exists in user config")):
            with self.assertRaisesRegex(ValueError, "already exists; refusing to overwrite"):
                install_claude_config(self.root, self.node, target, "claude")
        self.assertEqual(target.read_text(), '{"permissions":{"deny":[]}}')

    def test_claude_registration_failure_leaves_the_settings_alone(self):
        target = Path(self.tmp.name) / "settings.json"
        target.write_text('{"chrome":{"enabled":true}}')

        def fake_run(command, **_kwargs):
            return subprocess.CompletedProcess(command, 1, "", "registration failed")

        with patch("host_config_removal.subprocess.run", side_effect=fake_run):
            with self.assertRaisesRegex(ValueError, "registration failed"):
                install_claude_config(self.root, self.node, target, "claude")
        self.assertEqual(target.read_text(), '{"chrome":{"enabled":true}}')

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
