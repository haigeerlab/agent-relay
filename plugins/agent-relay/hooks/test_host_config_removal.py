"""Host MCP removal touches only exact Spec Guard entries; never real user configuration."""
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from host_config_removal import add_claude_server, remove_claude_server, remove_codex_table
import native_collaboration_adapters
from native_collaboration_runtime import BRIDGE_COMMIT


FRAGMENT = '[mcp_servers.spec_guard_x]\ncommand = "/opt/node"\n\n[mcp_servers.spec_guard_x.env]\nA = "1"\n'
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
                self.assertEqual(remove_codex_table(self.config, FRAGMENT, "spec_guard_x"), "removed")
                self.assertEqual(self.config.read_text(encoding="utf-8"), expected)
                self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)

    def test_absent_table_or_file_changes_nothing(self):
        self.assertEqual(remove_codex_table(self.config, FRAGMENT, "spec_guard_x"), "absent")
        self.assertFalse(self.config.exists())
        self.write(BEFORE)
        self.assertEqual(remove_codex_table(self.config, FRAGMENT, "spec_guard_x"), "absent")
        self.assertEqual(self.config.read_text(encoding="utf-8"), BEFORE)

    def test_edited_extended_duplicated_or_quoted_tables_are_left_for_the_user(self):
        cases = {
            "edited": BEFORE + "\n" + FRAGMENT.replace("/opt/node", "/usr/bin/node"),
            "extra key after the fragment": BEFORE + "\n" + FRAGMENT + 'B = "2"\n',
            "fragment twice": FRAGMENT + "\n" + FRAGMENT,
            "second quoted table": FRAGMENT + '\n[mcp_servers."spec_guard_x".extra]\nC = 1\n',
        }
        for name, original in cases.items():
            with self.subTest(name):
                self.write(original)
                with self.assertRaisesRegex(ValueError, r"at line \d+ differs .* remove it manually"):
                    remove_codex_table(self.config, FRAGMENT, "spec_guard_x")
                self.assertEqual(self.config.read_text(encoding="utf-8"), original)

    def test_refuses_a_symlinked_configuration(self):
        target = Path(self.tmp.name) / "real.toml"
        target.write_text(FRAGMENT, encoding="utf-8")
        self.config.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "not a symlink"):
            remove_codex_table(self.config, FRAGMENT, "spec_guard_x")
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


class NativeUninstallRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sg-native-uninstall-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "native"
        self.root.mkdir(mode=0o700)
        for name in ("mailbox", "mailbox/backups", "data"):
            (self.root / name).mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        self.node = Path(self.tmp.name) / "node"
        self.node.write_text("node\n")
        self.node.chmod(0o755)
        self.config = Path(self.tmp.name) / "config.toml"

    def cli(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            code = native_collaboration_adapters.main([
                *arguments, "--root", str(self.root), "--node", str(self.node),
                "--codex-config", str(self.config)])
        return code, output.getvalue()

    def test_install_then_uninstall_restores_the_original_file(self):
        original = BEFORE + "\n" + AFTER
        self.config.write_text(original, encoding="utf-8")
        self.config.chmod(0o600)
        self.assertEqual(self.cli("install-codex")[0], 0)
        self.assertIn("spec_guard_native_collaboration", self.config.read_text(encoding="utf-8"))
        self.assertEqual(self.cli("uninstall-codex")[0], 1)
        self.assertIn("spec_guard_native_collaboration", self.config.read_text(encoding="utf-8"))
        code, output = self.cli("uninstall-codex", "--confirm-uninstall")
        self.assertEqual((code, "removed" in output), (0, True))
        self.assertEqual(self.config.read_text(encoding="utf-8"), original.rstrip("\n") + "\n")

if __name__ == "__main__":
    unittest.main()
