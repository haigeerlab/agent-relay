"""The skills find their own code the way the host loaded it (acceptance-kit-round2 D53, round 2 R2-11).

Claude substitutes ${CLAUDE_PLUGIN_ROOT} in skill text with the copy the session loaded (for a directory marketplace,
its source; Task 1 probe); Codex has no substitution, so the enabled entry's source.path is used; otherwise the block
refuses. It never reads installed_plugins.json or guesses a cache directory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILLS = [PLUGIN_ROOT / "skills" / name / "SKILL.md" for name in ("collaboration-ops", "session-delegation",
                                                                  "session-routing")]
BLOCK = re.compile(r"<!-- agent-relay-root -->\n```bash\n(.*?)```\n<!-- /agent-relay-root -->", re.S)


def block(skill: Path) -> str:
    found = BLOCK.findall(skill.read_text(encoding="utf-8"))
    if len(found) != 1:
        raise AssertionError(f"{skill.parent.name}: expected one agent-relay-root block, found {len(found)}")
    return found[0]


class PluginRootTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-root-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()

    def resolve(self, text: str, codex_listing: dict | None) -> subprocess.CompletedProcess:
        if codex_listing is not None:
            (self.tmp / "codex.json").write_text(json.dumps(codex_listing), encoding="utf-8")
            codex = self.bin / "codex"
            codex.write_text(f'#!/bin/sh\ncat "{self.tmp}/codex.json"\n', encoding="utf-8")
            codex.chmod(0o755)
        env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(self.tmp)}
        return subprocess.run(["/bin/bash", "-c", text + '\necho "ROOT=$ROOT"'], capture_output=True, text=True,
                              env=env, timeout=30)

    def test_the_three_skills_carry_the_same_block_and_never_guess(self):
        blocks = {skill.parent.name: block(skill) for skill in SKILLS}
        self.assertEqual(len(set(blocks.values())), 1, "the block differs between skills")
        for skill in SKILLS:
            text = skill.read_text(encoding="utf-8")
            for forbidden in ("installed_plugins.json", "plugins/cache", "CLAUDE_PLUGIN_ROOT`;"):
                self.assertNotIn(forbidden, text, f"{skill.parent.name}: {forbidden}")

    def test_claude_uses_the_substituted_root(self):
        text = block(SKILLS[0]).replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN_ROOT))  # what Claude does at load
        done = self.resolve(text, {"installed": [{"name": "agent-relay", "enabled": True,
                                                  "source": {"path": "/elsewhere"}}]})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"ROOT={PLUGIN_ROOT}\n", done.stdout)

    def test_codex_uses_the_enabled_source_path(self):
        listing = {"installed": [{"name": "agent-relay", "enabled": False, "source": {"path": "/disabled"}},
                                 {"name": "agent-relay", "enabled": True, "source": {"path": str(PLUGIN_ROOT)}}]}
        done = self.resolve(block(SKILLS[1]), listing)  # unsubstituted: the shell sees an unset variable
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"ROOT={PLUGIN_ROOT}\n", done.stdout)

    def test_refuses_when_neither_host_names_a_root(self):
        for listing in (None, {"installed": []}, {"installed": [{"name": "agent-relay", "enabled": True,
                                                                  "source": {"path": str(self.tmp)}}]}):
            with self.subTest(listing=listing):
                done = self.resolve(block(SKILLS[2]), listing)
                self.assertEqual(done.returncode, 2)
                self.assertIn("cannot locate the agent-relay plugin root", done.stderr)
                self.assertNotIn("ROOT=", done.stdout)

    def test_claude_runs_the_selector_with_the_literal_path_the_allow_rule_names(self):
        text = SKILLS[2].read_text(encoding="utf-8")
        self.assertIn("python3 -B ${CLAUDE_PLUGIN_ROOT}/hooks/session_routing.py select", text)


if __name__ == "__main__":
    unittest.main()
