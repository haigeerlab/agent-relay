#!/usr/bin/env python3
"""Contract tests for the human-facing native collaboration entry."""
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "collab" / "SKILL.md"
OPS_SKILL = PLUGIN_ROOT / "skills" / "collaboration-ops" / "SKILL.md"
OPS_COMMAND = PLUGIN_ROOT / "commands" / "collaboration.md"
REFERENCE = PLUGIN_ROOT / "references" / "collaboration-runtime.md"
VALIDATE = PLUGIN_ROOT.parents[1] / "scripts" / "validate.sh"


class CollabEntryContractTest(unittest.TestCase):
    def skill_text(self) -> str:
        self.assertTrue(SKILL.is_file())
        return SKILL.read_text(encoding="utf-8")

    def test_short_natural_language_entry_and_scope(self):
        text = self.skill_text()
        for phrase in (
            # 「告诉某人一件事」的自然语言入口归 session-routing（见
            # test_session_routing_entry.py 的同名断言）：两个 skill 的 description
            # 曾经都宣称它，而选错是静默的 —— 正文会被复制进信箱而不走原生通道。
            "name: collab", "加入本机联调", "查看联调消息", "有哪些会话",
            "不创建 Ticket", "session-delegation", "session-routing",
        ):
            self.assertIn(phrase, text)

    def test_contacting_by_name_is_not_advertised_here(self):
        """The description must not compete with session-routing for that intent."""
        description = next(line for line in self.skill_text().splitlines()
                           if line.startswith("description:"))
        self.assertNotIn("告诉", description)
        self.assertIn("session-routing", description)

    def test_native_join_is_lazy_private_and_current_session_only(self):
        text = self.skill_text()
        for phrase in (
            "bridge_register", "bridge_sessions", "thisSession", "CODEX_THREAD_ID",
            "短随机后缀", "不能替另一个会话注册", "不猜窗口标题",
        ):
            self.assertIn(phrase, text)

    def test_wake_requires_opt_in_and_binds_in_any_permission_mode(self):
        # wake-any-mode D142, D143: opt-in still required; any mode binds; the session's own settings govern the turn.
        text = self.skill_text()
        self.assertLess(text.index("默认 `wake: null`"), text.index("明确要求"))
        self.assertNotIn("未开启自动批准", text)
        for phrase in ('wake: "auto"', '{app: "codex", sessionId:', "任何权限模式", "自己的权限设置决定",
                       "不改、不降", "不构成任何授权", "不一定经过用户本人"):
            self.assertIn(phrase, text)

    def test_directory_and_name_resolution_are_truthful(self):
        text = self.skill_text()
        for phrase in (
            "[Claude Code]", "[Codex]", "registered", "wakeable", "wake-held",
            "unread", "不等于在线", "唯一匹配才发送", "零匹配", "多匹配",
            "完整内部 ID",
            # presence-and-approval D146: presence words, and the user answers prompts themselves.
            "presence.state", "等待授权", "已停止", "不替用户回答",
            # long-messages D152, D153: long messages are read with the mailbox tools alone.
            "nextOffset", "bodyOffset", "不用 Bash", "不回显正文",
            # mailbox-polish D156: the one-time approval lines, never written for the user.
            "claude-allow-rules", "不要替用户改这个文件",
        ):
            self.assertIn(phrase, text)

    def test_send_ack_wait_and_unknown_are_independent(self):
        text = self.skill_text()
        for phrase in (
            "bridge_send", "bridge_inbox", "bridge_ack", "bridge_wait",
            "bridge_wake_status", "bridge_outbox", "acknowledgedAt",
            "acknowledge: false", "`unknown` 保持未知", "不重复发送",
        ):
            self.assertIn(phrase, text)

    def test_unavailable_native_runtime_has_no_alternate_transport(self):
        text = self.skill_text()
        for phrase in (
            "没有选择器、旧传输或自动回退", "没有 `bridge_*` 工具",
            "collaboration-ops", "不尝试第二条传输",
        ):
            self.assertIn(phrase, text)

    def test_operator_surfaces_are_explicit_and_history_preserving(self):
        for path in (OPS_SKILL, OPS_COMMAND):
            text = path.read_text(encoding="utf-8")
            self.assertIn("collab", text)
            self.assertIn("native_collaboration_runtime.py", text)
            self.assertIn("native_collaboration_adapters.py", text)
        reference = REFERENCE.read_text(encoding="utf-8")
        self.assertIn("A fresh plugin", reference)
        self.assertIn("keeping backlog", reference)

    def test_repository_validation_runs_the_entry_contract(self):
        self.assertIn(
            'TESTS_GLOB="plugins/agent-relay/hooks/test_*.py"',
            VALIDATE.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
