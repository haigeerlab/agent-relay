#!/usr/bin/env python3
"""Documentation promises for paused-session-link (D287–D293)."""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FILES = {
    "skill": REPO / "plugins/agent-relay/skills/collab/SKILL.md",
    "server": REPO / "plugins/agent-relay/bridge/src/server.ts",
    "interface": REPO / "docs/collaboration-interface.md",
    "notifications": REPO / "docs/notifications.md",
    "notifications_en": REPO / "docs/notifications.en.md",
    "hosts": REPO / "docs/host-differences.md",
    "changelog": REPO / "CHANGELOG.md",
}


class PausedSessionDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}

    def test_registration_and_server_instructions_keep_a_session_its_own_link(self):
        for name in ("skill", "server"):
            with self.subTest(name=name):
                text = self.text[name]
                self.assertIn("get_session", text)
                self.assertIn("self", text)
                self.assertIn("desktop", text)
                self.assertIn("another session's link", text)

    def test_interface_documents_desktop_and_version(self):
        text = self.text["interface"]
        self.assertIn("2.12", text)
        self.assertRegex(text, re.compile(r"bridge_register.*desktop", re.S))
        self.assertRegex(text, re.compile(r"bridge_agents.*desktop", re.S))

    def test_offline_notification_click_is_documented(self):
        for name in ("notifications", "notifications_en"):
            with self.subTest(name=name):
                text = self.text[name].lower()
                self.assertIn("offline", text)
                self.assertIn("link", text)
                self.assertTrue("click" in text or "点击" in text)

    def test_host_difference_records_measured_click(self):
        text = self.text["hosts"]
        h4 = text[text.index("## H4"):]
        self.assertIn("terminal-notifier", h4)
        self.assertTrue("process" in h4 or "进程" in h4)
        self.assertIn("get_session", h4)

    def test_changelog_names_interface_and_schema(self):
        text = self.text["changelog"]
        # The entry moves from [Unreleased] to its release section at release time: check the section that holds it.
        sections = re.split(r"\n(?=## \[)", text)
        holding = [section for section in sections if "paused-session-link" in section]
        self.assertEqual(len(holding), 1, "exactly one CHANGELOG section names paused-session-link")
        for value in ("desktop", "2.12", "schema 8"):
            self.assertIn(value, holding[0])

    def test_no_real_local_session_ids(self):
        allowed = {"local_<uuid>", "local_00000000-0000-4000-8000-000000000001"}
        pattern = re.compile(r"local_[0-9a-fA-F-]+|local_<uuid>")
        for name, text in self.text.items():
            with self.subTest(name=name):
                self.assertEqual(set(pattern.findall(text)) - allowed, set())


if __name__ == "__main__":
    unittest.main()
