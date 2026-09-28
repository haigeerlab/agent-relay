"""Opt-in native bridge runtime tests; never fetch upstream or change host settings."""
import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_collaboration_runtime import (BRIDGE_COMMIT, NativeRuntimeError,
                                          install_runtime, probe_runtime, status)



# 固定提交 8f12c880 的 server.ts 实际注册的 17 个工具（逐字写死，不从被测常量推导）。
PINNED_TOOLS = [
    "ask_codex", "bridge_ack", "bridge_agents", "bridge_continue_codex", "bridge_inbox",
    "bridge_orchestrate_codex", "bridge_orchestration_status", "bridge_orchestration_wait",
    "bridge_outbox", "bridge_register", "bridge_retire", "bridge_send", "bridge_sessions",
    "bridge_thread", "bridge_wait", "bridge_wake_status", "review_with_codex",
]

class NativeCollaborationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sg-native-runtime-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "native"

    def test_status_is_read_only_when_runtime_is_absent(self):
        self.assertEqual(status(self.root), {"state": "absent"})
        self.assertFalse(self.root.exists())

    def test_installer_pins_source_and_disables_dependency_scripts(self):
        commands = []
        self.root.parent.chmod(0o755)  # Existing ~/.spec-guard may be readable; stage is private.

        def fake_run(command, **kwargs):
            commands.append(command)
            if command[:2] == ["node", "--version"]:
                return subprocess.CompletedProcess(command, 0, "v22.5.0\n", "")
            if command[-2:] == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, BRIDGE_COMMIT + "\n", "")
            if command[:3] == ["npm", "run", "build"]:
                (Path(kwargs["cwd"]) / "dist").mkdir()
                (Path(kwargs["cwd"]) / "dist" / "server.js").write_text("server\n")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            installed = install_runtime(self.root)
        self.assertEqual(installed["state"], "ready")
        self.assertEqual(status(self.root)["commit"], BRIDGE_COMMIT)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.root / "data").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.root / "mailbox" / "backups").stat().st_mode), 0o700)
        self.assertTrue(any(command[:2] == ["git", "fetch"] and command[-1] == BRIDGE_COMMIT
                            for command in commands))
        self.assertTrue(any(command[:2] == ["npm", "ci"] and "--ignore-scripts" in command
                            for command in commands))
        self.assertFalse(any("setup" in command for command in commands))

    def test_status_rejects_world_readable_or_symlinked_runtime(self):
        self.root.mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "mailbox").mkdir(mode=0o700)
        (self.root / "mailbox" / "backups").mkdir(mode=0o700)
        (self.root / "data").mkdir(mode=0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        self.root.chmod(0o755)
        self.assertEqual(status(self.root)["state"], "invalid")
        self.root.chmod(0o700)
        self.assertEqual(status(self.root)["state"], "ready")
        linked = Path(self.tmp.name) / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(status(linked)["state"], "invalid")
        database = self.root / "mailbox" / "bridge.sqlite"
        database.symlink_to(self.root / "manifest.json")
        self.assertEqual(status(self.root)["state"], "invalid")
        database.unlink()
        (self.root / "dist" / "server.js").unlink()
        (self.root / "dist").rmdir()
        (self.root / "dist").symlink_to(self.root / "mailbox", target_is_directory=True)
        self.assertEqual(status(self.root)["state"], "invalid")

    def test_status_rejects_public_or_symlinked_backups(self):
        self.root.mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "mailbox").mkdir(mode=0o700)
        backups = self.root / "mailbox" / "backups"
        backups.mkdir(mode=0o700)
        (self.root / "data").mkdir(mode=0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        backups.chmod(0o755)
        self.assertEqual(status(self.root)["state"], "invalid")
        backups.chmod(0o700)
        backup = backups / "bridge-daily-2026-09-25.sqlite"
        backup.write_bytes(b"backup")
        backup.chmod(0o644)
        self.assertEqual(status(self.root)["state"], "invalid")
        backup.unlink()
        backups.rmdir()
        backups.symlink_to(self.root / "data", target_is_directory=True)
        self.assertEqual(status(self.root)["state"], "invalid")

    def test_installer_rejects_existing_target_and_old_node_without_mutation(self):
        self.root.mkdir()
        with self.assertRaisesRegex(NativeRuntimeError, "already exists"):
            install_runtime(self.root)
        self.root.rmdir()
        with patch("native_collaboration_runtime.subprocess.run", return_value=
                   subprocess.CompletedProcess(["node", "--version"], 0, "v20.0.0\n", "")):
            with self.assertRaisesRegex(NativeRuntimeError, "22.5"):
                install_runtime(self.root)
        self.assertFalse(self.root.exists())

    def test_wrong_fetched_commit_never_activates_runtime(self):
        def fake_run(command, **_kwargs):
            output = "v22.5.0\n" if command[:2] == ["node", "--version"] else ""
            if command[-2:] == ["rev-parse", "HEAD"]:
                output = "0" * 40 + "\n"
            return subprocess.CompletedProcess(command, 0, output, "")

        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            with self.assertRaisesRegex(NativeRuntimeError, "does not match"):
                install_runtime(self.root)
        self.assertFalse(self.root.exists())

    def test_probe_uses_throwaway_mailbox_and_reports_mcp_startup(self):
        self.root.mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "mailbox").mkdir(mode=0o700)
        (self.root / "mailbox" / "backups").mkdir(mode=0o700)
        (self.root / "data").mkdir(mode=0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))

        def fake_run(command, **kwargs):
            self.assertEqual(command[1], str(self.root / "dist" / "server.js"))
            self.assertNotEqual(kwargs["env"]["BRIDGE_DB_PATH"],
                                str(self.root / "mailbox" / "bridge.sqlite"))
            self.assertTrue(kwargs["env"]["BRIDGE_DB_PATH"].startswith(str(self.root)))
            self.assertEqual(kwargs["env"]["BRIDGE_BACKUPS"], "0")
            self.assertIn('"method": "tools/list"', kwargs["input"])
            return subprocess.CompletedProcess(command, 0, self.catalog(PINNED_TOOLS), "")

        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            self.assertEqual(probe_runtime(self.root, node="node"),
                             {"state": "ready", "toolCount": 17})
        self.assertEqual(list(self.root.glob("native-probe-*")), [])
        self.assertFalse((self.root / "mailbox" / "bridge.sqlite").exists())

    def test_probe_fails_closed_on_startup_error_or_missing_tools(self):
        self.root.mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "mailbox").mkdir(mode=0o700)
        (self.root / "mailbox" / "backups").mkdir(mode=0o700)
        (self.root / "data").mkdir(mode=0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        with patch("native_collaboration_runtime.subprocess.run", return_value=
                   subprocess.CompletedProcess(["node"], 1, "", "private path or error")):
            self.assertEqual(probe_runtime(self.root)["state"], "invalid")
        with patch("native_collaboration_runtime.subprocess.run", return_value=
                   subprocess.CompletedProcess(["node"], 0,
                       '{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\n', "")):
            self.assertEqual(probe_runtime(self.root)["state"], "invalid")
        with patch("native_collaboration_runtime.subprocess.run", return_value=
                   subprocess.CompletedProcess(["node"], 0, '[]\n', "")):
            self.assertEqual(probe_runtime(self.root)["state"], "invalid")
        with patch("native_collaboration_runtime.subprocess.run", side_effect=
                   subprocess.TimeoutExpired(["node"], 15)):
            self.assertIn("TimeoutExpired", probe_runtime(self.root)["diagnostic"])
        with patch("native_collaboration_runtime.subprocess.run", return_value=
                   subprocess.CompletedProcess(["node"], 0, self.catalog(
                       [tool for tool in PINNED_TOOLS if tool != "bridge_wait"]), "")):
            self.assertIn("incomplete", probe_runtime(self.root)["diagnostic"])

    def test_probe_rejects_an_upstream_tool_nobody_reviewed(self):
        self.root.mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        for name in ("mailbox", "data"):
            (self.root / name).mkdir(mode=0o700)
        (self.root / "mailbox" / "backups").mkdir(mode=0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        with patch("native_collaboration_runtime.subprocess.run", return_value=
                   subprocess.CompletedProcess(["node"], 0, self.catalog(
                       PINNED_TOOLS + ["bridge_run_shell"]), "")):
            self.assertEqual(probe_runtime(self.root), {
                "state": "invalid",
                "diagnostic": "native MCP exposes unreviewed tools: bridge_run_shell"})

    @staticmethod
    def catalog(names):
        return json.dumps({"jsonrpc": "2.0", "id": 2,
                           "result": {"tools": [{"name": name} for name in names]}}) + "\n"


if __name__ == "__main__":
    unittest.main()
