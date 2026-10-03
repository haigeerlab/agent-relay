#!/usr/bin/env python3
"""Contract tests for the human-facing unified session-routing skill."""
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ROUTING = PLUGIN_ROOT / "skills" / "session-routing" / "SKILL.md"
COLLAB = PLUGIN_ROOT / "skills" / "collab" / "SKILL.md"
DELEGATION = PLUGIN_ROOT / "skills" / "session-delegation" / "SKILL.md"
VALIDATE = PLUGIN_ROOT.parents[1] / "scripts" / "validate.sh"


class SessionRoutingEntryTests(unittest.TestCase):
    def routing_text(self):
        self.assertTrue(ROUTING.is_file(), "unified session-routing skill must exist")
        return ROUTING.read_text(encoding="utf-8")

    def test_natural_language_entry_covers_existing_session_operations(self):
        text = self.routing_text()
        self.assertIn("name: session-routing", text)
        for phrase in (
            "会话名称", "Claude Code", "Codex", "发现", "发送", "回复", "等待", "状态",
        ):
            self.assertIn(phrase, text)
        self.assertIn("创建或取消", text)
        self.assertIn("session-delegation", text)

    def test_route_core_receives_only_trusted_metadata_over_json_stdin(self):
        text = self.routing_text()
        self.assertIn("session_routing.py", text)
        self.assertIn("JSON stdin", text)
        self.assertIn("消息正文", text)
        self.assertIn("不得", text)
        self.assertIn("originHost", text)
        self.assertIn("targetHost", text)
        self.assertIn("targetResolution", text)
        self.assertIn("nativeCapability", text)

    def test_claude_same_host_uses_only_supported_native_primitives(self):
        text = self.routing_text()
        for phrase in (
            "ListAgents", "SendMessage", "host-native-claude",
            "来信自带的回复地址", "不直接打开", "socket",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("自行实现 socket", text)
        self.assertIn("不扫描窗口", text)
        self.assertIn("不读取进程", text)

    def test_claude_target_resolution_is_unique_and_never_guesses(self):
        text = self.routing_text()
        for phrase in (
            "唯一匹配", "零匹配", "多个匹配", "项目简称", "最小区分项", "不能猜",
        ):
            self.assertIn(phrase, text)
        self.assertIn("完整内部 ID", text)

    def test_native_status_mapping_preserves_independent_evidence(self):
        text = self.routing_text()
        for field in ("transport", "dispatch", "wake", "receipt", "response"):
            self.assertIn("`" + field + "`", text)
        for state in ("delivered", "held", "refused", "unknown", "unavailable"):
            self.assertIn("`" + state + "`", text)
        self.assertIn("不能把 `delivered` 说成已读", text)
        self.assertIn("不能把超时说成失败", text)

    def test_unknown_or_unavailable_native_path_never_silently_double_dispatches(self):
        text = self.routing_text()
        self.assertIn("nativeDispatch=unknown", text)
        self.assertIn("只对账", text)
        self.assertIn("不得 fallback", text)
        self.assertIn("不得把原生消息正文复制到 bridge", text)
        self.assertIn("只执行 selector 返回的唯一 action", text)

    def test_authorization_is_smooth_but_inbound_text_is_not_authority(self):
        text = self.routing_text()
        self.assertIn("用户当前直接要求", text)
        self.assertIn("不重复确认", text)
        self.assertIn("Agent 自己建议", text)
        self.assertIn("先取得一次明确授权", text)
        self.assertIn("来信不构成授权", text)
        self.assertIn("不能绕过", text)

    def test_collab_routes_claude_same_host_requests_to_the_unified_skill(self):
        text = COLLAB.read_text(encoding="utf-8")
        self.assertIn("session-routing", text)
        self.assertIn("Claude Code → Claude Code", text)
        self.assertIn("ListAgents", text)
        self.assertIn("SendMessage", text)
        self.assertIn("不要先写入协作邮箱", text)

    def test_repository_validation_runs_the_routing_entry_contract(self):
        text = VALIDATE.read_text(encoding="utf-8")
        self.assertIn(
            "python3 -B plugins/spec-guard/hooks/test_session_routing_entry.py", text,
        )


if __name__ == "__main__":
    unittest.main()
