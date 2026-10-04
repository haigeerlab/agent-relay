"""The normal collab skill exposes the native mailbox without a second command."""
from pathlib import Path
import unittest


SKILL = Path(__file__).resolve().parents[1] / "skills" / "collab" / "SKILL.md"


class NativeCollabEntryTests(unittest.TestCase):
    def text(self):
        return SKILL.read_text(encoding="utf-8")

    def test_one_native_mailbox_and_no_implicit_fallback(self):
        text = self.text()
        self.assertIn("唯一邮箱", text)
        self.assertIn("native bridge", text)
        self.assertIn("不尝试第二条传输", text)

    def test_current_session_wake_binding_is_verified(self):
        text = self.text()
        for phrase in (
            "默认 `wake: null`", "明确要求", "自动批准", "bridge_sessions",
            "thisSession", "CODEX_THREAD_ID", "不能替另一个会话注册",
        ):
            self.assertIn(phrase, text)

    def test_mailbox_handling_is_honest_and_idempotent(self):
        text = self.text()
        for phrase in (
            "bridge_agents", "bridge_send", "bridge_inbox", "bridge_ack",
            "bridge_outbox", "bridge_wake_status", "acknowledge: false",
            "连续消息复用", "不重复注册", "`unknown` 保持未知",
        ):
            self.assertIn(phrase, text)

    def test_sender_cannot_bind_an_unbound_target(self):
        text = self.text()
        self.assertIn("未绑定时只入箱", text)
        self.assertIn("不能替另一个会话", text)

    def test_cross_host_targeting_uses_host_project_and_name(self):
        text = self.text()
        for phrase in ("目标宿主", "会话名称", "项目", "唯一匹配", "零匹配", "多匹配"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
