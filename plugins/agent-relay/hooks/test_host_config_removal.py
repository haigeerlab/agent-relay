"""Host MCP removal touches only exact agent-relay entries; never real user configuration."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from host_config_removal import add_claude_server, remove_claude_server, remove_codex_table


FRAGMENT = '[mcp_servers.agent_relay_x]\ncommand = "/opt/node"\n\n[mcp_servers.agent_relay_x.env]\nA = "1"\n'
BEFORE = '[mcp_servers.chrome]\ncommand = "chrome"\n'
AFTER = '[desktop]\nfollowUpQueueMode = "queue"\n'


class RemoveCodexTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sg-host-removal-")
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / "config.toml"

    def write(self, text, mode=0o600):
        self.config.write_text(text, encoding="utf-8")
        self.config.chmod(mode)

    def test_removes_the_exact_table_and_keeps_neighbours_byte_for_byte(self):
        for original, expected in (
                (BEFORE + "\n" + FRAGMENT + "\n" + AFTER, BEFORE + "\n" + AFTER),
                (BEFORE + "\n" + FRAGMENT, BEFORE),
                (FRAGMENT + "\n" + AFTER, AFTER),
                (FRAGMENT, "")):
            with self.subTest(original=original):
                self.write(original, 0o640)
                self.assertEqual(remove_codex_table(self.config, FRAGMENT, "agent_relay_x"), "removed")
                self.assertEqual(self.config.read_text(encoding="utf-8"), expected)
                self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)

    def test_absent_table_or_file_changes_nothing(self):
        self.assertEqual(remove_codex_table(self.config, FRAGMENT, "agent_relay_x"), "absent")
        self.assertFalse(self.config.exists())
        self.write(BEFORE)
        self.assertEqual(remove_codex_table(self.config, FRAGMENT, "agent_relay_x"), "absent")
        self.assertEqual(self.config.read_text(encoding="utf-8"), BEFORE)

    def test_edited_extended_duplicated_or_quoted_tables_are_left_for_the_user(self):
        cases = {
            "edited": BEFORE + "\n" + FRAGMENT.replace('A = "1"', 'A = "2"'),
            "extra key after the fragment": BEFORE + "\n" + FRAGMENT + 'B = "2"\n',
            "fragment twice": FRAGMENT + "\n" + FRAGMENT,
            "second quoted table": FRAGMENT + '\n[mcp_servers."agent_relay_x".extra]\nC = 1\n',
        }
        for name, original in cases.items():
            with self.subTest(name):
                self.write(original)
                with self.assertRaisesRegex(ValueError, r"at line \d+ differs .* remove it manually"):
                    remove_codex_table(self.config, FRAGMENT, "agent_relay_x")
                self.assertEqual(self.config.read_text(encoding="utf-8"), original)

    def test_refuses_a_symlinked_configuration(self):
        target = Path(self.tmp.name) / "real.toml"
        target.write_text(FRAGMENT, encoding="utf-8")
        self.config.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "not a symlink"):
            remove_codex_table(self.config, FRAGMENT, "agent_relay_x")
        self.assertEqual(target.read_text(encoding="utf-8"), FRAGMENT)


class RemoveClaudeServerTests(unittest.TestCase):
    def test_absent_server_is_reported_from_the_remove_result(self):
        # 真实 CLI（2026-09-28 实测）：rc=1，输出 `No MCP server named "x" in user scope`。
        with patch("host_config_removal.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 1, "", 'No MCP server named "x" in user scope')) as run:
            self.assertEqual(remove_claude_server("claude", "x"), "absent")
        self.assertEqual(run.call_count, 1)

    def test_existing_server_is_removed_without_a_slow_health_check(self):
        with patch("host_config_removal.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, "Removed", "")) as run:
            self.assertEqual(remove_claude_server("claude", "x"), "removed")
        self.assertEqual([call.args[0] for call in run.call_args_list],
                         [["claude", "mcp", "remove", "--scope", "user", "x"]])

    def test_refused_or_unrunnable_removal_is_an_error(self):
        with patch("host_config_removal.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 1, "", "permission denied")):
            with self.assertRaisesRegex(ValueError, "refused to remove"):
                remove_claude_server("claude", "x")
        with patch("host_config_removal.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(["claude"], 30)):
            with self.assertRaisesRegex(ValueError, "unable to run"):
                remove_claude_server("claude", "x")


class AddClaudeServerTests(unittest.TestCase):
    def test_registers_with_a_single_add_call(self):
        with patch("host_config_removal.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, "Added", "")) as run:
            add_claude_server("claude", ["add", "--scope", "user", "x", "--", "cmd"], "x")
        self.assertEqual([call.args[0] for call in run.call_args_list],
                         [["claude", "mcp", "add", "--scope", "user", "x", "--", "cmd"]])

    def test_existing_name_and_other_failures_are_distinct_errors(self):
        for output, pattern in (
                ("MCP server x already exists in user config", "already exists; refusing"),
                ("Invalid command path", "rejected MCP registration for x: Invalid command path")):
            with self.subTest(output=output), patch(
                    "host_config_removal.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 1, "", output)):
                with self.assertRaisesRegex(ValueError, pattern):
                    add_claude_server("claude", ["add", "x"], "x")
        with patch("host_config_removal.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(["claude"], 30)):
            with self.assertRaisesRegex(ValueError, "unable to run"):
                add_claude_server("claude", ["add", "x"], "x")



# safe-uninstall (round 1 finding 6): Codex adds approval subtables when the user chooses 始终允许.
MAIN = '[mcp_servers.agent_relay]\ncommand = "/opt/node"\nargs = ["/r/server.js"]\nenabled_tools = ["bridge_send"]\n'
ENV = '[mcp_servers.agent_relay.env]\nBRIDGE_DB_PATH = "/r/bridge.sqlite"\n'
REAL_FRAGMENT = MAIN + "\n" + ENV
APPROVALS = "".join('\n[mcp_servers.agent_relay.tools.%s]\napproval_mode = "approve"\n' % tool
                    for tool in ("bridge_register", "bridge_inbox", "bridge_agents", "bridge_wait", "bridge_ack"))


class ApprovalSubtableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ar-approval-")
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / "config.toml"

    def write(self, text):
        self.config.write_text(text, encoding="utf-8")
        self.config.chmod(0o600)

    def remove(self):
        return remove_codex_table(self.config, REAL_FRAGMENT, "agent_relay")

    def test_this_macs_shape_is_removed_with_its_five_approval_subtables(self):
        self.write(BEFORE + "\n" + REAL_FRAGMENT + APPROVALS + "\n" + AFTER)
        self.assertEqual(self.remove(), "removed")
        self.assertEqual(self.config.read_text(encoding="utf-8"), BEFORE + "\n" + AFTER)

    def test_approval_subtables_anywhere_with_any_mode_and_comments_are_removed(self):
        text = (REAL_FRAGMENT + "\n" + AFTER + '\n[mcp_servers."agent_relay".tools.bridge_send]\n# chosen in the app\n'
                "approval_mode = 'prompt'\n\n" + BEFORE)
        self.write(text)
        self.assertEqual(self.remove(), "removed")
        self.assertEqual(self.config.read_text(encoding="utf-8"), AFTER + "\n" + BEFORE)

    def test_a_different_node_path_is_accepted_when_it_is_an_executable(self):
        node = Path(self.tmp.name) / "node"
        node.write_text("#!/bin/sh\n")
        node.chmod(0o700)
        self.write(REAL_FRAGMENT.replace("/opt/node", str(node)) + APPROVALS)
        self.assertEqual(self.remove(), "removed")
        self.assertEqual(self.config.read_text(encoding="utf-8"), "")
        self.write(REAL_FRAGMENT.replace("/opt/node", str(Path(self.tmp.name) / "missing-node")))
        with self.assertRaisesRegex(ValueError, r"line 2: command"):
            self.remove()

    def test_other_differences_refuse_and_name_each_line_without_values(self):
        cases = {
            "extra key in the main table": (MAIN + 'secret_hint = "tok-123"\n\n' + ENV + APPROVALS,
                                            [r"line 5: unexpected key secret_hint"]),
            "changed env value": (MAIN + "\n" + ENV.replace("/r/bridge.sqlite", "/elsewhere") + APPROVALS,
                                  [r"line 7: BRIDGE_DB_PATH differs"]),
            "approval subtable with a second key": (
                REAL_FRAGMENT + '\n[mcp_servers.agent_relay.tools.bridge_send]\napproval_mode = "approve"\nnote = "x"\n',
                [r"line 11: unexpected key note in \[mcp_servers.agent_relay.tools.bridge_send\]"]),
            "unknown subtable": (REAL_FRAGMENT + '\n[mcp_servers.agent_relay.extra]\nC = 1\n',
                                 [r"line 9: unexpected table \[mcp_servers.agent_relay.extra\]"]),
            "missing env key": (MAIN + "\n[mcp_servers.agent_relay.env]\n", [r"missing BRIDGE_DB_PATH"]),
            "main table twice": (REAL_FRAGMENT + "\n" + MAIN, [r"line 9: duplicate table"]),
        }
        for name, (text, patterns) in cases.items():
            with self.subTest(name):
                self.write(text)
                with self.assertRaises(ValueError) as raised:
                    self.remove()
                message = str(raised.exception)
                self.assertIn("remove it manually", message)
                for pattern in patterns:
                    self.assertRegex(message, pattern)
                self.assertNotIn("tok-123", message, "values are never printed")
                self.assertEqual(self.config.read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()
