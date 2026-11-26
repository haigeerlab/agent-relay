#!/usr/bin/env python3
"""Documentation promises for idle-wake-batching (D299–D308)."""
import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "plugins/agent-relay"
FILES = {
    "interface": REPO / "docs/collaboration-interface.md",
    "collab": PLUGIN / "skills/collab/SKILL.md",
    "session-routing": PLUGIN / "skills/session-routing/SKILL.md",
    "readme": REPO / "README.md",
    "changelog": REPO / "CHANGELOG.md",
}
SINCE = "Since interface 2.14 (`idle-wake-batching` D299–D305)"


class IdleHoldDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}

    def interface_row(self, name):
        row = re.search(rf"^\| `{re.escape(name)}` \| .*", self.text["interface"], re.M)
        self.assertIsNotNone(row, f"Missing interface row for {name}")
        return row.group()

    def test_interface_marker_is_2_14(self):
        marker = json.loads((PLUGIN / "interface.json").read_text(encoding="utf-8"))
        self.assertEqual(marker["interface"], "2.14")

    def test_header_names_next_interface_and_mailbox_schema(self):
        note = re.search(r"^- \*\*Interface version\.\*\*.*?(?=\n- )", self.text["interface"], re.M | re.S)
        self.assertIsNotNone(note)
        next_release = " ".join(note.group().split())
        self.assertRegex(next_release, r"The next release implements `2\.14` \(`idle-wake-batching`")
        self.assertIn("mailbox schema 9 (`wake_jobs.explicit_wake`)", next_release)

    def test_bridge_send_documents_omitted_and_explicit_wake_and_warning(self):
        row = self.interface_row("bridge_send")
        for value in (
            SINCE,
            "If `wake` is omitted, its ping may be held for an idle Claude recipient when the message needs no reply",
            "`wake: true` always pings",
            "D305 warning",
            '"<agent>" has been idle for N min; this message needs no reply, so its ping is held and goes out '
            "with its next wake (see bridge_outbox).",
        ):
            with self.subTest(value=value):
                self.assertIn(value, row)

    def test_wake_views_document_idle_and_unknown_pending_reasons(self):
        for name in ("bridge_outbox", "bridge_wake_status"):
            with self.subTest(name=name):
                row = self.interface_row(name)
                for value in (SINCE, '`pendingReason: "idle"`', "treat an unknown `pendingReason` as pending"):
                    self.assertIn(value, row)

    def test_cli_send_documents_explicit_wake(self):
        row = self.interface_row("send --from <script identity> --to <agent>")
        self.assertIn(SINCE, row)
        self.assertIn("`--wake`", row)

    def test_skills_explain_when_to_request_a_reply_or_force_a_wake(self):
        for skill in ("collab", "session-routing"):
            with self.subTest(skill=skill):
                wording = " ".join(self.text[skill].split())
                for value in (
                    "要对方回答的消息用 `expectsReply: true`",
                    "只有对方空闲也必须马上叫醒（例如用户在等）时才写 `wake: true`",
                    "纯通知两者都不写",
                    "唤醒显示 `idle`",
                    "提醒被攒住了，等收件方下次醒来一起送到，消息没有丢",
                ):
                    self.assertIn(value, wording)

    def test_readme_documents_idle_threshold(self):
        self.assertIn("`BRIDGE_IDLE_HOLD_MS`", self.text["readme"])

    def test_changelog_section_names_idle_hold_and_runtime_upgrade(self):
        section = re.search(r"^## \[[^\]]+\][^\n]*\n(?:(?!\n## \[).)*?idle-wake-batching.*?(?=\n## \[|\Z)", self.text["changelog"], re.M | re.S)
        self.assertIsNotNone(section)
        for value in ("idle-wake-batching", "schema 8 → 9", "`upgrade --confirm`"):
            self.assertIn(value, section.group())


if __name__ == "__main__":
    unittest.main()
