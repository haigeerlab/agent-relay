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
        # 这个意图从 collab 的 description 搬到这里，不能两边都没有：
        # 用户说「告诉可乐……」时必须有一个 skill 宣称它。
        description = next(line for line in text.splitlines()
                           if line.startswith("description:"))
        self.assertIn("告诉", description)
        self.assertIn("collab", description)

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

    def test_codex_same_host_uses_supported_task_turn_operations(self):
        text = self.routing_text()
        for phrase in (
            "list_threads", "read_thread", "send_message_to_thread", "wait_threads",
            "host-native-codex", "精确 task 引用", "task/turn",
        ):
            self.assertIn(phrase, text)
        self.assertIn("thread/start", text)
        self.assertIn("turn/start", text)
        self.assertIn("thread/resume", text)

    def test_codex_bidirectional_contract_preserves_host_authorization_boundary(self):
        text = self.routing_text()
        self.assertIn("目标在该 turn 内返回 assistant reply", text)
        self.assertIn("来源用 `wait_threads` 或 `read_thread`", text)
        self.assertIn("不能要求目标 task 主动跨 task 回发", text)
        self.assertIn("转述授权", text)
        self.assertIn("当前发送 task", text)

    def test_codex_never_guesses_private_identity_or_adds_a_model_override(self):
        text = self.routing_text()
        for phrase in (
            "不能按标题", "不读取 Codex 私有状态", "不扫描进程",
            "不使用 PATH 中的旧 Codex", "不传 `--model`",
        ):
            self.assertIn(phrase, text)
        self.assertIn("标题和项目只用于向用户做最小消歧", text)

    def test_codex_response_loss_reconciles_exact_turn_without_resending(self):
        text = self.routing_text()
        self.assertIn("afterCursor", text)
        self.assertIn("响应丢失", text)
        self.assertIn("不能再次调用 `send_message_to_thread`", text)
        self.assertIn("timeout", text)
        self.assertIn("response=unknown", text)

    def test_delegation_routes_existing_session_messages_without_creating_a_duplicate(self):
        text = DELEGATION.read_text(encoding="utf-8")
        self.assertIn("已有会话", text)
        self.assertIn("session-routing", text)
        self.assertIn("不得为了传话创建新会话", text)

    def test_cross_host_routes_both_directions_to_one_selected_bridge(self):
        text = self.routing_text()
        self.assertIn("Claude Code → Codex", text)
        self.assertIn("Codex → Claude Code", text)
        self.assertIn("spec-guard-bridge", text)
        self.assertIn("native runtime", text)
        for state in ("invalid", "unavailable"):
            self.assertIn("`" + state + "`", text)
        self.assertIn("不切换到其他传输", text)

    def test_same_host_fallback_never_joins_or_configures_to_improve_its_grade(self):
        text = self.routing_text()
        for phrase in (
            "当前授权仍覆盖", "两端已经唯一 bridge-joined", "bridge 已 ready",
            "fallbackFrom", "routeReason", "不再逐条确认",
        ):
            self.assertIn(phrase, text)
        self.assertIn("fallback 前不得懒注册", text)
        self.assertIn("不能启动服务", text)
        self.assertIn("不能修改配置", text)

    def test_unified_directory_labels_host_source_and_only_proven_facts(self):
        text = self.routing_text()
        for phrase in (
            "[Claude Code]", "[Codex]", "native-visible", "bridge-joined",
            "项目简称", "liveness", "wake", "unread", "last activity",
        ):
            self.assertIn(phrase, text)
        self.assertIn("不能把 bridge-joined 说成 online", text)
        self.assertIn("不扫描未注册窗口", text)
        self.assertIn("不自动注册每个新会话", text)

    def test_bridge_outcome_keeps_enqueue_wake_ack_and_reply_independent(self):
        text = self.routing_text()
        self.assertIn("enqueue", text)
        self.assertIn("wake admission", text)
        self.assertIn("acknowledgement", text)
        self.assertIn("reply", text)
        self.assertIn("入箱不等于 wake", text)
        self.assertIn("acknowledged 不等于 response=received", text)

    def test_collab_routes_codex_native_and_cross_host_through_the_same_selector(self):
        text = COLLAB.read_text(encoding="utf-8")
        self.assertIn("Codex ↔ Codex", text)
        self.assertIn("host-native-codex", text)
        self.assertIn("跨宿主", text)
        self.assertIn("native bridge", text)
        self.assertIn("session-routing", text)

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
        self.assertIn("Claude Code ↔ Claude Code", text)
        self.assertIn("ListAgents", text)
        self.assertIn("SendMessage", text)
        self.assertIn("不复制正文到 bridge", text)

    def test_repository_validation_runs_the_routing_entry_contract(self):
        text = VALIDATE.read_text(encoding="utf-8")
        self.assertIn(
            "python3 -B plugins/spec-guard/hooks/test_session_routing_entry.py", text,
        )


if __name__ == "__main__":
    unittest.main()
