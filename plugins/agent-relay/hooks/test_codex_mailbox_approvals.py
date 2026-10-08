"""install-codex pre-approves the mailbox tools for Codex (codex-gated-wake D70).

A woken Codex turn runs under the user's approval gate (D65); the ten mailbox tools only read and write the mailbox,
so their `approval_mode = "approve"` subtables let Codex read and reply without a card, while any execution still
meets the read-only sandbox. Existing installs add them with `--approve-mailbox-tools`. Nothing goes to ~/.codex/rules.
"""
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import native_collaboration_adapters
from native_collaboration_adapters import CODEX_SERVER_NAME, codex_fragment
from native_collaboration_runtime import BRIDGE_COMMIT, MAILBOX_TOOLS

BEFORE = '[mcp_servers.chrome]\ncommand = "chrome"\n'


def approval(tool):
    return f'[mcp_servers.{CODEX_SERVER_NAME}.tools.{tool}]\napproval_mode = "approve"\n'


class MailboxApprovalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-approvals-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / "native"
        self.root.mkdir(mode=0o700)
        for name in ("mailbox", "mailbox/backups", "data"):
            (self.root / name).mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        self.node = self.base / "node"
        self.node.write_text("#!/bin/sh\necho v24.18.0\n")
        self.node.chmod(0o755)
        self.home = self.base / "home"
        (self.home / ".codex").mkdir(parents=True)
        self.config = self.home / ".codex" / "config.toml"

    def cli(self, *arguments):
        out = io.StringIO()
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", ""), "CODEX_HOME": str(self.home / ".codex")}
        with patch.dict(os.environ, env, clear=True), redirect_stdout(out), redirect_stderr(out):
            try:
                code = native_collaboration_adapters.main([
                    *arguments, "--root", str(self.root), "--node", str(self.node), "--codex-config", str(self.config)])
            except SystemExit as error:
                code = error.code
        return code, out.getvalue()

    def tables(self):
        return re.findall(r"^\[mcp_servers\.agent_relay\.tools\.(\w+)\]$", self.config.read_text(), re.M)

    def test_fresh_install_pre_approves_exactly_the_mailbox_tools(self):
        self.config.write_text(BEFORE)
        code, output = self.cli("install-codex")
        self.assertEqual(code, 0, output)
        self.assertEqual(sorted(self.tables()), sorted(MAILBOX_TOOLS))
        text = self.config.read_text()
        for tool in MAILBOX_TOOLS:
            self.assertIn(approval(tool), text)
        for tool in ("ask_codex", "bridge_retire", "bridge_orchestrate_codex"):
            self.assertNotIn(f".tools.{tool}]", text)
        self.assertFalse((self.home / ".codex" / "rules").exists())

    def test_install_then_uninstall_restores_the_file(self):
        self.config.write_text(BEFORE)
        self.assertEqual(self.cli("install-codex")[0], 0)
        code, output = self.cli("uninstall-codex", "--confirm-uninstall")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.config.read_text(), BEFORE)

    def test_uninstall_removes_approval_tables_left_for_removed_worker_tools(self):
        # orchestrator-removal D92: whatever 始终允许 wrote under our server, including for a tool removed since, goes.
        self.config.write_text(BEFORE)
        self.assertEqual(self.cli("install-codex")[0], 0)
        self.config.write_text(self.config.read_text() + "\n" + approval("ask_codex") + "\n" + approval("bridge_retire"))
        code, output = self.cli("uninstall-codex", "--confirm-uninstall")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.config.read_text(), BEFORE)

    def test_the_option_adds_only_missing_tables_to_a_matching_entry(self):
        # An entry from before this module, plus one table the user wrote with 始终允许.
        self.config.write_text(BEFORE + "\n" + codex_fragment(self.root, self.node) + "\n" + approval("bridge_inbox"))
        code, output = self.cli("install-codex", "--approve-mailbox-tools")
        self.assertEqual(code, 0, output)
        self.assertIn("9 mailbox tool", output)
        tables = self.tables()
        self.assertEqual(sorted(tables), sorted(MAILBOX_TOOLS), "each tool once; the user's table kept")
        self.assertTrue(any(path.name == "config.toml" for path in (self.home / ".agent-relay").rglob("*")),
                        "backed up first")
        code, output = self.cli("install-codex", "--approve-mailbox-tools")
        self.assertEqual(code, 0, output)
        self.assertIn("already", output)
        code, output = self.cli("uninstall-codex", "--confirm-uninstall")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.config.read_text().strip(), BEFORE.strip())

    def test_the_option_refuses_without_a_matching_entry(self):
        self.config.write_text(BEFORE)
        before = self.config.read_bytes()
        code, output = self.cli("install-codex", "--approve-mailbox-tools")
        self.assertNotEqual(code, 0)
        self.assertIn("not installed", output)
        changed = BEFORE + "\n" + codex_fragment(self.root, self.node).replace("tool_timeout_sec = 300", "tool_timeout_sec = 9")
        self.config.write_text(changed)
        code, output = self.cli("install-codex", "--approve-mailbox-tools")
        self.assertNotEqual(code, 0)
        self.assertIn("tool_timeout_sec differs", output)
        self.assertEqual(self.config.read_text(), changed)
        self.assertNotEqual(before, b"")


if __name__ == "__main__":
    unittest.main()
