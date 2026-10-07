"""The bridge runs on the node the host entries pin, or nothing happens (round2-fixes D50, round 2 R2-1 and R2-7)."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from native_collaboration_doctor import doctor
from node_select import NodeSelectError, select_node
from session_delegation_control import main as control_main


def fake_node(path: Path, version: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho {version}\n")
    path.chmod(0o755)
    return path


class Homes(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-node-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.old = fake_node(self.base / "nvm12" / "node", "v12.22.12")
        self.new = fake_node(self.base / "nvm24" / "node", "v24.18.0")
        self.brew = fake_node(self.base / "brew" / "node", "v22.5.0")
        self.claude_json = self.base / ".claude.json"
        self.codex_config = self.base / "config.toml"

    def pin_claude(self, node: Path):
        self.claude_json.write_text(json.dumps({"mcpServers": {"agent-relay": {"command": str(node), "args": []}}}))

    def pin_codex(self, node: Path):
        self.codex_config.write_text(f'[mcp_servers.agent_relay]\ncommand = "{node}"\nargs = []\n')

    def select(self, explicit=None, path_node=None):
        return select_node(explicit, claude_json=self.claude_json, codex_config=self.codex_config,
                           which=lambda _name: None if path_node is None else str(path_node))


class SelectNodeTests(Homes):
    def test_order_is_explicit_then_claude_entry_then_codex_entry_then_path(self):
        self.pin_claude(self.new)
        self.pin_codex(self.brew)
        self.assertEqual((self.select(self.brew, self.old).source, self.select(self.brew, self.old).path),
                         ("--node", self.brew))
        self.assertEqual((self.select(path_node=self.old).source, self.select(path_node=self.old).path),
                         ("claude-entry", self.new))
        self.claude_json.unlink()
        self.assertEqual(self.select(path_node=self.old).source, "codex-entry")
        self.assertEqual(self.select(path_node=self.old).version, "v22.5.0")
        self.codex_config.unlink()
        with self.assertRaises(NodeSelectError) as caught:
            self.select(path_node=self.old)
        self.assertEqual(caught.exception.reason, "node-too-old")

    def test_an_entry_naming_a_missing_node_falls_through(self):
        self.pin_claude(self.base / "gone" / "node")
        self.assertEqual(self.select(path_node=self.new).source, "PATH")

    def test_too_old_says_where_which_version_and_why(self):
        self.pin_claude(self.old)
        with self.assertRaises(NodeSelectError) as caught:
            self.select(path_node=self.new)
        detail = caught.exception.detail
        for needle in (str(self.old), "claude-entry", "v12.22.12", "22.5.0", "node:sqlite"):
            self.assertIn(needle, detail)

    def test_unavailable_cases(self):
        with self.assertRaisesRegex(NodeSelectError, "node-unavailable"):
            self.select(self.base / "missing")
        with self.assertRaisesRegex(NodeSelectError, "node-unavailable"):
            self.select()
        garbage = fake_node(self.base / "odd" / "node", "hello")
        with self.assertRaisesRegex(NodeSelectError, "node-unavailable"):
            self.select(garbage)


class ControllerRefusesBeforeAnyWriteTests(Homes):
    def run_control(self, argv, prompt="Review the diff"):
        output = io.StringIO()
        environment = {"CODEX_THREAD_ID": "thread-1", "PATH": str(self.old.parent),
                       "CLAUDE_CONFIG_DIR": str(self.base), "CODEX_HOME": str(self.base)}
        with mock.patch.dict(os.environ, environment, clear=True), redirect_stdout(output), \
                mock.patch("sys.stdin", io.StringIO(prompt)):
            code = control_main(argv)
        return code, json.loads(output.getvalue())

    def test_create_with_only_an_old_node_refuses_and_writes_nothing(self):
        state_root = self.base / "state"
        code, payload = self.run_control([
            "--state-root", str(state_root), "--native-root", str(self.base / "runtime"), "create",
            "--origin-host", "codex", "--target-host", "claude", "--project", str(self.base),
            "--repo-identity", "git:example/project", "--baseline", "a" * 40, "--expires-at", "1800000000",
            "--idempotency-key", "node-old", "--launch-key", "node-old", "--name", "复审", "--summary", "Review",
        ])
        self.assertEqual(code, 1)
        self.assertEqual(payload["reason"], "node-too-old")
        self.assertIn("v12.22.12", payload["detail"])
        self.assertFalse(state_root.exists())

    def test_status_continue_cancel_and_permissions_refuse_the_same_way(self):
        state_root = self.base / "state"
        state_root.mkdir(mode=0o700)
        before = sorted(state_root.iterdir())
        for argv in (["status", "--name", "x"], ["cancel", "--name", "x"], ["continue", "--name", "x"],
                     ["permissions", "--project", str(self.base)]):
            with self.subTest(command=argv[0]):
                code, payload = self.run_control(
                    ["--state-root", str(state_root), "--native-root", str(self.base / "runtime"), *argv])
                self.assertEqual((code, payload["reason"]), (1, "node-too-old"))
        self.assertEqual(sorted(state_root.iterdir()), before)

    def test_the_pinned_node_is_used_when_path_is_old(self):
        self.pin_claude(self.new)
        with mock.patch("session_delegation_backend.resolve_backend") as resolve:
            resolve.side_effect = ValueError("stop-after-selection")
            code, payload = self.run_control([
                "--state-root", str(self.base / "state"), "--native-root", str(self.base / "runtime"),
                "permissions", "--project", str(self.base)])
        self.assertEqual(payload["reason"], "stop-after-selection")
        self.assertEqual(resolve.call_args.kwargs["node"], self.new)


class DoctorProbeNodeTests(Homes):
    def test_doctor_probes_with_the_pinned_node_and_names_it(self):
        from test_runtime_upgrade import fake_run
        from native_collaboration_runtime import install_runtime

        root = self.base / "runtime"
        with mock.patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            install_runtime(root)
        self.pin_claude(self.new)
        used = []

        def probe(_root, node):
            used.append(node)
            return {"state": "ready", "toolCount": 17}

        with mock.patch.dict(os.environ, {"PATH": str(self.old.parent)}), \
                mock.patch("native_collaboration_doctor._probe_outside", side_effect=probe):
            report = doctor(root, home=self.base, claude_json=self.claude_json, codex_config=self.codex_config,
                            processes=lambda: [], alive=lambda _pid: False)
        check = next(check for check in report["checks"] if check["check"] == "probe")
        self.assertEqual(used, [str(self.new)])
        self.assertEqual(check["state"], "ok")
        self.assertIn(str(self.new), check["detail"])
        self.assertIn("v24.18.0", check["detail"])

    def test_doctor_reports_an_old_node_as_a_probe_failure_with_the_reason(self):
        from test_runtime_upgrade import fake_run
        from native_collaboration_runtime import install_runtime

        root = self.base / "runtime"
        with mock.patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            install_runtime(root)
        with mock.patch.dict(os.environ, {"PATH": str(self.old.parent)}):
            report = doctor(root, home=self.base, claude_json=self.claude_json, codex_config=self.codex_config,
                            processes=lambda: [], alive=lambda _pid: False)
        check = next(check for check in report["checks"] if check["check"] == "probe")
        self.assertEqual(check["state"], "fail")
        self.assertIn("node:sqlite", check["detail"])


if __name__ == "__main__":
    unittest.main()
