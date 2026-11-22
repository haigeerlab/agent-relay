#!/usr/bin/env python3
"""Local path privacy (S107): no tracked file names a real macOS account in a home path.

Sample names are joined at run time, so this file never holds a real-looking home path itself.
"""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "check_local_paths.py"

HOME = "/Users/"
ENCODED = "-Users-"


def load_checker():
    module_spec = importlib.util.spec_from_file_location("check_local_paths", SCRIPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class HitsTest(unittest.TestCase):
    def setUp(self):
        self.check = load_checker()

    def test_a_real_style_home_path_is_caught(self):
        for text in (HOME + "alice" + "/Documents/repo", "cd " + HOME + "j.doe-2", "Read(/" + HOME + "bob" + "/x/**)"):
            self.assertEqual(self.check.hits_in_text("ok\n" + text + "\n"), [(2, "path")], text)

    def test_the_encoded_form_is_caught(self):
        text = "~/.claude/projects/" + ENCODED + "alice" + "-Documents-repo/"
        self.assertEqual(self.check.hits_in_text(text), [(1, "encoded")])

    def test_allowed_names_and_placeholders_pass(self):
        clean = [HOME + name + "/project" for name in sorted(self.check.ALLOWED)]
        clean += [ENCODED + "x" + "-Documents", HOME + "<user>" + "/Documents/repo", ENCODED + "<user>" + "-Documents",
                  "~/Documents/repo", "$HOME/.agent-relay", "/home/alice/x", "Users/alice"]
        for text in clean:
            self.assertEqual(self.check.hits_in_text(text), [], text)

    def test_one_bad_name_among_allowed_ones_is_caught(self):
        self.assertEqual(self.check.hits_in_text(HOME + "example" + "/a " + HOME + "carol" + "/b"), [(1, "path")])


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.check = load_checker()

    def test_scan_reports_file_and_line_never_the_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True)
            (Path(tmp) / "a.md").write_text("fine\n" + HOME + "alice" + "/x\n")
            (Path(tmp) / "b.bin").write_bytes(b"\0" + (HOME + "alice" + "/x").encode())
            (Path(tmp) / "untracked.md").write_text(HOME + "alice" + "/x\n")
            subprocess.run(["git", "-C", tmp, "add", "a.md", "b.bin"], check=True)
            hits = self.check.scan(tmp)
        self.assertEqual(hits, ["a.md:2: path"])
        self.assertNotIn("alice", " ".join(hits))

    def test_the_repository_has_no_local_home_path(self):
        self.assertGreater(len(self.check.tracked_files()), 50, "the scan found too few files to mean anything")
        self.assertEqual(self.check.scan(), [],
                         "replace the account name with a placeholder: ~/..., $HOME/... or /Users/<user>/...")


if __name__ == "__main__":
    unittest.main()
