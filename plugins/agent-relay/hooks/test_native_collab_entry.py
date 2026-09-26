"""The normal collab skill must have one safe native path, not a second command."""
from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parents[1] / "skills" / "collab" / "SKILL.md"


class NativeCollabEntryTests(unittest.TestCase):
    def test_one_entry_selects_one_backend_without_implicit_fallback(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("collaboration_backend.py", text)
        self.assertIn("`native`", text)
        self.assertIn("`xats`", text)
        self.assertIn("不得自动退回 XATS", text)

    def test_native_join_binds_only_the_current_host_session(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in ("bridge_register", "bridge_sessions", "CODEX_THREAD_ID", "wake: \"auto\"",
                       "wake: {app: \"codex\", sessionId:", "不得要求用户提供任务 ID"):
            self.assertIn(phrase, text)

    def test_native_mailbox_has_honest_handling_and_safe_name_resolution(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in ("bridge_agents", "bridge_send", "bridge_inbox", "bridge_ack",
                       "bridge_outbox", "bridge_wake_status", "acknowledge: false",
                       "只在唯一匹配时", "不构成授权"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
