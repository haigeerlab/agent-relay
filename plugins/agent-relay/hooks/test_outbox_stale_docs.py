#!/usr/bin/env python3
"""Documentation promises for outbox-stale-filter (D294–D298)."""
import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
FILES = {
    "interface": REPO / "docs/collaboration-interface.md",
    "skill": REPO / "plugins/agent-relay/skills/collab/SKILL.md",
    "changelog": REPO / "CHANGELOG.md",
}


class OutboxStaleDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}

    def test_interface_marker_is_at_least_2_13(self):
        marker = json.loads((REPO / "plugins/agent-relay/interface.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(tuple(int(p) for p in marker["interface"].split(".")), (2, 13))

    def test_interface_documents_outbox_stale_filter_and_cli_default(self):
        text = self.text["interface"]
        outbox = re.search(r"\| `bridge_outbox` .*?(?=\n\| `bridge_agents`)", text, re.S)
        self.assertIsNotNone(outbox)
        for value in ("includeStale", "hiddenStale", "2.13", "left out by default"):
            self.assertIn(value, outbox.group())
        cli = re.search(r"\| `outbox <agent>` .*", text)
        self.assertIsNotNone(cli)
        self.assertIn("same default", cli.group())

    def test_collab_skill_reports_and_can_include_stale_messages(self):
        text = self.text["skill"]
        for value in ("hiddenStale", "includeStale", "另有 N 条已过期或收件方已退役，未列出"):
            self.assertIn(value, text)

    def test_changelog_section_names_module(self):
        sections = re.findall(r"\n## \[[^\]]+\].*?(?=\n## \[|\Z)", self.text["changelog"], re.S)
        self.assertTrue(sections)
        section = next((item for item in sections if "outbox-stale-filter" in item), None)
        self.assertIsNotNone(section)
        self.assertIn("2.13", section)


if __name__ == "__main__":
    unittest.main()
