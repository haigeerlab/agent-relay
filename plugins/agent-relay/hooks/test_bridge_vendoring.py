"""The vendored bridge matches its recorded hashes and keeps its provenance (bridge-vendoring, D23)."""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from native_collaboration_runtime import BRIDGE_COMMIT, BRIDGE_SOURCE, NativeRuntimeError, verify_bridge_copy


class VendoredBridgeTests(unittest.TestCase):
    def test_the_vendored_tree_matches_upstream_sha256(self):
        verify_bridge_copy(BRIDGE_SOURCE)

    def test_provenance_and_licence_are_kept(self):
        upstream = (BRIDGE_SOURCE / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn(BRIDGE_COMMIT, upstream)
        self.assertIn("github.com/WebisityStudio/claude-codex-mcp-bridge", upstream)
        licence = (BRIDGE_SOURCE / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(licence.startswith("MIT License\n\nCopyright (c) 2026 Tesla Major"))

    def test_left_out_upstream_paths_are_absent(self):
        for name in ("skills", "agents", "assets", ".github", "scripts/generate-demo-gif.py"):
            self.assertFalse((BRIDGE_SOURCE / name).exists(), name)

    def test_any_unrecorded_change_is_refused(self):
        for change in ("edit", "add", "remove"):
            with self.subTest(change=change), tempfile.TemporaryDirectory(prefix="ar-bridge-") as tmp:
                copy = Path(tmp) / "bridge"
                shutil.copytree(BRIDGE_SOURCE, copy)
                if change == "edit":
                    with (copy / "src" / "server.ts").open("a", encoding="utf-8") as handle:
                        handle.write("\n")
                elif change == "add":
                    (copy / "src" / "extra.ts").write_text("export {};\n", encoding="utf-8")
                else:
                    (copy / "src" / "paths.ts").unlink()
                with self.assertRaisesRegex(NativeRuntimeError, "differs from UPSTREAM.sha256"):
                    verify_bridge_copy(copy)


if __name__ == "__main__":
    unittest.main()
