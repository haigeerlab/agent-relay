"""Opt-in native bridge runtime tests; never fetch upstream or change host settings."""
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from native_collaboration_runtime import (BRIDGE_COMMIT, BRIDGE_SOURCE, NativeRuntimeError,
                                          UPSTREAM_TREE, bridge_tree, default_root,
                                          install_runtime, probe_runtime, status)



# The ten tools the bridge registers since orchestrator-removal (written out, not taken from the constant under test).
SERVED_TOOLS = [
    "bridge_ack", "bridge_agents", "bridge_inbox", "bridge_outbox", "bridge_register",
    "bridge_send", "bridge_sessions", "bridge_thread", "bridge_wait", "bridge_wake_status",
]
# The seven worker tools a 0.4.0 bridge registered and hosts were told to deny (written out, not taken from the
# constant under test); orchestrator-removal removed them, and uninstall still cleans up what 0.4.0 wrote.
LEGACY_NAMES = ("bridge_retire", "ask_codex", "review_with_codex", "bridge_orchestrate_codex",
                "bridge_continue_codex", "bridge_orchestration_wait", "bridge_orchestration_status")


class NativeCollaborationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sg-native-runtime-")
        self.addCleanup(self.tmp.cleanup)
        # These tests pin the default (variable unset) layout under a patched home.
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("AGENT_RELAY_HOME", None)
        self.root = Path(self.tmp.name) / "native"

    def test_default_root_is_the_runtime_directory_under_agent_relay(self):
        # Decision D9: ~/.agent-relay holds runtime/, delegation/ and backups/; install refuses an
        # existing root, so the runtime cannot be ~/.agent-relay itself.
        home = Path(self.tmp.name) / "home"
        with patch("native_collaboration_runtime.Path.home", return_value=home):
            self.assertEqual(default_root(), home / ".agent-relay" / "runtime")

    def test_default_install_creates_a_private_agent_relay_parent(self):
        home = Path(self.tmp.name) / "home"
        home.mkdir()

        def fake_run(command, **kwargs):
            if command[:2] == ["node", "--version"]:
                return subprocess.CompletedProcess(command, 0, "v22.5.0\n", "")
            if command[:3] == ["npm", "run", "build"]:
                (Path(kwargs["cwd"]) / "dist").mkdir()
                (Path(kwargs["cwd"]) / "dist" / "server.js").write_text("server\n")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("native_collaboration_runtime.Path.home", return_value=home), \
                patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            installed = install_runtime(default_root())
        self.assertEqual(installed["state"], "ready")
        self.assertEqual(stat.S_IMODE((home / ".agent-relay").stat().st_mode), 0o700)
        self.assertTrue((home / ".agent-relay" / "runtime" / "manifest.json").is_file())

    def test_status_is_read_only_when_runtime_is_absent(self):
        self.assertEqual(status(self.root), {"state": "absent"})
        self.assertFalse(self.root.exists())

    def test_installer_pins_source_and_disables_dependency_scripts(self):
        commands = []
        self.root.parent.chmod(0o755)  # Existing ~/.agent-relay may be readable; stage is private.

        def fake_run(command, **kwargs):
            commands.append(command)
            if command[:2] == ["node", "--version"]:
                return subprocess.CompletedProcess(command, 0, "v22.5.0\n", "")
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
        # bridge-vendoring D24: built from the plugin's verified copy, never fetched with git.
        self.assertFalse(any(command[0] == "git" for command in commands))
        self.assertTrue((self.root / "src" / "server.ts").is_file())
        self.assertTrue(any(command[:2] == ["npm", "ci"] and "--ignore-scripts" in command
                            for command in commands))
        self.assertFalse(any("setup" in command for command in commands))
        # D26: the manifest marks a vendored install and its tree.
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest, {"commit": BRIDGE_COMMIT, "source": "vendored",
                                    "tree": bridge_tree(BRIDGE_SOURCE)})
        self.assertEqual(status(self.root)["bridge"],
                         {"source": "vendored", "tree": bridge_tree(BRIDGE_SOURCE), "current": True})

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
            return subprocess.CompletedProcess(command, 0, self.catalog(SERVED_TOOLS), "")

        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            self.assertEqual(probe_runtime(self.root, node="node"),
                             {"state": "ready", "toolCount": 10})
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
                       [tool for tool in SERVED_TOOLS if tool != "bridge_wait"]), "")):
            self.assertEqual(probe_runtime(self.root)["diagnostic"],
                             "native MCP mailbox tools are incomplete: missing bridge_wait")

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
                       SERVED_TOOLS + ["bridge_run_shell"]), "")):
            self.assertEqual(probe_runtime(self.root), {
                "state": "invalid",
                "diagnostic": "native MCP exposes tools beyond the ten mailbox tools: bridge_run_shell"})

    def test_probe_rejects_a_removed_worker_tool_too(self):
        # orchestrator-removal D91: the tool set is the server's job; a 0.4.0 runtime serving the worker tools fails.
        self.root.mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        for name in ("mailbox", "data"):
            (self.root / name).mkdir(mode=0o700)
        (self.root / "mailbox" / "backups").mkdir(mode=0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        for extra in (["ask_codex"], list(LEGACY_NAMES)):
            with patch("native_collaboration_runtime.subprocess.run", return_value=
                       subprocess.CompletedProcess(["node"], 0, self.catalog(SERVED_TOOLS + extra), "")):
                result = probe_runtime(self.root)
            self.assertEqual(result["state"], "invalid", extra)
            self.assertEqual(result["diagnostic"],
                             "native MCP exposes tools beyond the ten mailbox tools: " + ", ".join(sorted(extra)))

    @staticmethod
    def catalog(names):
        return json.dumps({"jsonrpc": "2.0", "id": 2,
                           "result": {"tools": [{"name": name} for name in names]}}) + "\n"


    def ready_fixture(self, manifest):
        self.root.mkdir(mode=0o700)
        for sub in ("mailbox", "mailbox/backups", "data"):
            (self.root / sub).mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps(manifest))

    def test_status_tells_a_legacy_git_install_from_a_vendored_one(self):
        self.ready_fixture({"commit": BRIDGE_COMMIT})
        legacy = status(self.root)
        self.assertEqual(legacy["state"], "ready")
        self.assertEqual(legacy["bridge"], {"source": "upstream-git", "tree": None,
                                            "current": bridge_tree(BRIDGE_SOURCE) == UPSTREAM_TREE})
        (self.root / "manifest.json").write_text(json.dumps(
            {"commit": BRIDGE_COMMIT, "source": "vendored", "tree": "0" * 64}))
        stale = status(self.root)
        self.assertEqual(stale["state"], "ready")
        self.assertEqual(stale["bridge"], {"source": "vendored", "tree": "0" * 64, "current": False})
        for manifest in ({"commit": "f" * 40}, {"commit": BRIDGE_COMMIT, "source": "other"},
                         {"commit": BRIDGE_COMMIT, "source": "vendored", "tree": "short"}):
            (self.root / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(status(self.root)["state"], "invalid", manifest)

    def test_the_plugin_copy_has_moved_past_the_upstream_tree(self):
        # delivery-state-machine changed the bridge, so a git-installed 8f12c88 runtime is no longer current.
        self.assertNotEqual(bridge_tree(BRIDGE_SOURCE), UPSTREAM_TREE)

    def test_install_refuses_a_tampered_copy_before_running_npm(self):
        import shutil
        copy = Path(self.tmp.name) / "bridge"
        shutil.copytree(BRIDGE_SOURCE, copy)
        with (copy / "src" / "server.ts").open("a", encoding="utf-8") as handle:
            handle.write("\n")
        commands = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "v22.5.0\n", "")

        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run), \
                self.assertRaisesRegex(NativeRuntimeError, "differs from UPSTREAM.sha256"):
            install_runtime(self.root, source=copy)
        self.assertFalse(self.root.exists())
        self.assertFalse(any(command[0] == "npm" for command in commands))


if __name__ == "__main__":
    unittest.main()
