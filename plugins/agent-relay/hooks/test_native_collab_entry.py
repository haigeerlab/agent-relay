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

    def test_native_join_registers_without_wake_by_default(self):
        text = SKILL.read_text(encoding="utf-8")
        start = text.index("## 实验性 native 路径")
        end = text.index("## 当前 XATS 路径")
        native = text[start:end]
        self.assertIn("默认以 `wake: null` 登记", native)
        # The old unconditional binding instruction must be gone.
        self.assertNotIn("2. Claude Code 先用", native)
        # Binding phrases appear only after the explicit-opt-in condition.
        opt_in = native.index("明确要求")
        for phrase in ("wake: \"auto\"", "wake: {app: \"codex\", sessionId:"):
            self.assertIn(phrase, native)
            self.assertGreater(native.index(phrase), opt_in)
        self.assertLess(native.index("默认以 `wake: null` 登记"), opt_in)
        condition = native[opt_in:native.index("wake: \"auto\"")]
        self.assertIn("自动批准", condition)

    def test_native_wake_opt_in_keeps_current_session_verification(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in ("bridge_register", "bridge_sessions", "thisSession", "CODEX_THREAD_ID",
                       "不得要求用户提供任务 ID"):
            self.assertIn(phrase, text)

    def test_native_join_reports_whether_wake_is_bound(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("报告本会话是否绑定了唤醒", text)
        self.assertIn("bridge_inbox", text)

    def test_native_mailbox_has_honest_handling_and_safe_name_resolution(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in ("bridge_agents", "bridge_send", "bridge_inbox", "bridge_ack",
                       "bridge_outbox", "bridge_wake_status", "acknowledge: false",
                       "只在唯一匹配时", "不构成授权"):
            self.assertIn(phrase, text)

    def test_unavailable_native_tools_never_fall_back_to_leftover_xats_tools(self):
        text = SKILL.read_text(encoding="utf-8")
        for phrase in ("没有 `bridge_*` 工具或它们连接失败", "collaboration-ops",
                       "也不得改用它们"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
