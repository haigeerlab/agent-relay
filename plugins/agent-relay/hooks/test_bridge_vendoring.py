"""The vendored bridge matches its recorded hashes and keeps its provenance (bridge-vendoring, D23)."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest

from native_collaboration_runtime import (BRIDGE_COMMIT, BRIDGE_MANIFEST, BRIDGE_SOURCE, NOT_RUNTIME_FILES, RUNTIME_FILES,
                                          UPSTREAM_RUNTIME_MARK, UPSTREAM_TREE, NativeRuntimeError, _listed,
                                          _runtime_mark, runtime_mark, verify_bridge_copy)


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


class RuntimeMarkTests(unittest.TestCase):
    """runtime-mark-scope D248: the mark covers the bridge files the runtime is built from, nothing else."""

    def setUp(self):
        self.listed = (BRIDGE_SOURCE / BRIDGE_MANIFEST).read_bytes()

    def edited(self, name: str) -> bytes:
        lines = self.listed.decode("utf-8").splitlines()
        found = [index for index, line in enumerate(lines) if line.partition("  ")[2] == name]
        self.assertEqual(len(found), 1, name)
        lines[found[0]] = "0" * 64 + "  " + name
        return ("\n".join(lines) + "\n").encode("utf-8")

    def test_every_listed_path_is_classified_exactly_once(self):
        for line in self.listed.decode("utf-8").splitlines():
            name = line.partition("  ")[2]
            with self.subTest(name=name):
                self.assertEqual([_listed(name, RUNTIME_FILES), _listed(name, NOT_RUNTIME_FILES)].count(True), 1)

    def test_the_mark_ignores_tests_and_docs(self):
        first_test = next(line.partition("  ")[2] for line in self.listed.decode("utf-8").splitlines()
                          if line.partition("  ")[2].startswith("test/"))
        for name in (first_test, "docs/BACKGROUND-WAKE.md", "README.md", "CHANGELOG.md", "INSTRUCTIONS.md",
                     "LICENSE", ".gitignore", "tsconfig.test.json"):
            with self.subTest(name=name):
                self.assertEqual(_runtime_mark(self.edited(name)), _runtime_mark(self.listed))

    def test_the_mark_follows_every_runtime_file(self):
        for name in ("src/server.ts", "package.json", "package-lock.json", "tsconfig.json", "scripts/build.mjs"):
            with self.subTest(name=name):
                self.assertNotEqual(_runtime_mark(self.edited(name)), _runtime_mark(self.listed))

    def test_the_mark_of_a_directory_reads_its_list(self):
        self.assertEqual(runtime_mark(BRIDGE_SOURCE), _runtime_mark(self.listed))

    def test_the_legacy_mark_is_that_of_the_unmodified_8f12c88_list(self):
        # testdata/upstream-8f12c88.sha256 is the list first committed in 483756c, before any bridge change.
        listed = (Path(__file__).resolve().parent / "testdata" / "upstream-8f12c88.sha256").read_bytes()
        self.assertEqual(hashlib.sha256(listed).hexdigest(), UPSTREAM_TREE)
        self.assertEqual(_runtime_mark(listed), UPSTREAM_RUNTIME_MARK)


if __name__ == "__main__":
    unittest.main()
