"""Native collaboration Codex install and uninstall round-trip through the shared host-config helpers."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import native_collaboration_adapters
from native_collaboration_runtime import BRIDGE_COMMIT


BEFORE = '[mcp_servers.chrome]\ncommand = "chrome"\n'
AFTER = '[desktop]\nfollowUpQueueMode = "queue"\n'


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
