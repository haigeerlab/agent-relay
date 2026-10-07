"""Host adapters write the node the host entries pin, never PATH's first one (adapter-node D58, round 2 R2-13)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_collaboration_adapters import codex_fragment, main
from native_collaboration_runtime import BRIDGE_COMMIT


def script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return path


class AdapterNodeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-adapter-node-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.old = script(self.base / "nvm12" / "node", "echo v12.22.12")
        self.new = script(self.base / "nvm24" / "node", "echo v24.18.0")
        self.relay = self.base / "relay"
        self.root = self.relay / "runtime"
        for sub in ("mailbox/backups", "data", "dist"):
            (self.root / sub).mkdir(parents=True, mode=0o700)
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        for directory in (self.root, self.root / "mailbox", self.root / "mailbox" / "backups", self.root / "data"):
            directory.chmod(0o700)
        self.home = self.base / "home"
        self.home.mkdir()
        self.claude_json = self.home / ".claude.json"
        self.codex = self.base / "config.toml"
        self.codex.write_text('model = "x"\n')
        self.claude = script(self.base / "claude", "exit 0")
        self.settings = self.base / "settings.json"
        self.settings.write_text("{}")

    def pin_claude(self, node: Path):
        self.claude_json.write_text(json.dumps({"mcpServers": {"agent-relay": {"command": str(node)}}}))

    def run_main(self, *argv):
        env = {"PATH": f"{self.old.parent}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(self.home),
               "CLAUDE_CONFIG_DIR": str(self.home), "CODEX_HOME": str(self.home / ".codex"),
               "AGENT_RELAY_HOME": str(self.relay)}
        out = io.StringIO()
        with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(out):
            try:
                code = main([argv[0], "--root", str(self.root), "--codex-config", str(self.codex),
                             "--claude-json", str(self.claude_json), "--claude-settings", str(self.settings),
                             "--claude-bin", str(self.claude), *argv[1:]])
            except SystemExit as error:
                code = error.code
        return code, out.getvalue()

    def backups(self):
        return sorted((self.relay / "backups").glob("*")) if (self.relay / "backups").exists() else []

    def test_install_codex_writes_the_pinned_node_when_path_starts_with_an_old_one(self):
        self.pin_claude(self.new)
        code, output = self.run_main("install-codex")
        self.assertEqual(code, 0, output)
        text = self.codex.read_text()
        self.assertIn(f'command = "{self.new}"', text)
        self.assertNotIn(str(self.old), text)

    def test_printed_configurations_use_the_pinned_node(self):
        self.pin_claude(self.new)
        for command in ("codex", "claude"):
            with self.subTest(command=command):
                code, output = self.run_main(command)
                self.assertEqual(code, 0, output)
                self.assertIn(str(self.new), output)
                self.assertNotIn(str(self.old), output)

    def test_only_an_old_node_refuses_before_any_backup_or_write(self):
        before = self.codex.read_bytes()
        for argv in (("install-codex",), ("install-claude",), ("install-codex", "--node", str(self.old)),
                     ("codex",)):
            with self.subTest(argv=argv):
                code, output = self.run_main(*argv)
                self.assertNotEqual(code, 0, output)
                self.assertIn("node-too-old", output)
                self.assertIn("node:sqlite", output)
        self.assertEqual(self.codex.read_bytes(), before)
        self.assertEqual(self.backups(), [])

    def test_uninstall_codex_never_refuses_on_the_node(self):
        self.codex.write_text('model = "x"\n' + codex_fragment(self.root, self.new))
        code, output = self.run_main("uninstall-codex", "--confirm-uninstall")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.codex.read_text(), 'model = "x"\n')


if __name__ == "__main__":
    unittest.main()
