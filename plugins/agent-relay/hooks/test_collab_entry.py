#!/usr/bin/env python3
"""Contract tests for the human-facing collaboration entry skill."""

from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SKILL = PLUGIN_ROOT / "skills" / "collab" / "SKILL.md"
OPS_SKILL = PLUGIN_ROOT / "skills" / "collaboration-ops" / "SKILL.md"
OPS_COMMAND = PLUGIN_ROOT / "commands" / "collaboration.md"
PROTOCOL = PLUGIN_ROOT / "references" / "collaboration-protocol.md"
VALIDATE = PLUGIN_ROOT.parents[1] / "scripts" / "validate.sh"


class CollabEntryContractTest(unittest.TestCase):
    def skill_text(self) -> str:
        self.assertTrue(SKILL.is_file(), "daily collab skill must exist")
        return SKILL.read_text(encoding="utf-8")

    def test_skill_is_named_for_the_short_cross_host_entry(self) -> None:
        text = self.skill_text()

        self.assertIn("name: collab", text)
        for intent in ("加入本机联调", "查看联调消息", "告诉"):
            self.assertIn(intent, text)

    def test_one_step_join_hides_xats_registration_details(self) -> None:
        text = self.skill_text()

        for contract in (
            "register_agent",
            'team="spec-guard-local"',
            "project_dir",
            'agent_type="claude-code"',
            'agent_type="custom"',
            'agent_type_name="codex-desktop-native"',
        ):
            self.assertIn(contract, text)

        self.assertIn("不要向用户索取", text)
        for hidden_detail in ("team", "PID", "agent_type", "project_dir"):
            self.assertIn(hidden_detail, text)

    def test_daily_entry_reads_mailbox_without_starting_or_configuring_services(self) -> None:
        text = self.skill_text()
        prose = " ".join(text.split())

        self.assertIn("get_inbox", text)
        self.assertIn("list_agents", text)
        self.assertIn("不得自动初始化", text)
        self.assertIn("不得自动启动", text)
        self.assertIn("不得修改 Claude 或 Codex 的用户级 配置", prose)
        self.assertIn("ChatGPT in Chrome", text)

    def test_operator_surfaces_route_daily_use_to_collab(self) -> None:
        for path in (OPS_SKILL, OPS_COMMAND):
            text = path.read_text(encoding="utf-8")
            self.assertIn("collab", text)
            self.assertIn("日常", text)

    def test_operator_guidance_warns_against_general_preview_wake(self) -> None:
        ops = OPS_SKILL.read_text(encoding="utf-8")
        reference = (PLUGIN_ROOT / "references" / "collaboration-runtime.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("--enable-channel-wake", ops)
        self.assertIn("Claude Code CLI", reference)
        self.assertIn("ChatGPT in Chrome", reference)
        self.assertIn("研究预览", reference)
        self.assertIn("不要用", reference)
        self.assertIn("未观察到实际唤醒", reference)

    def test_operator_guidance_exposes_opt_in_tmux_cli_wake_without_overclaiming(self) -> None:
        ops = OPS_SKILL.read_text(encoding="utf-8")
        reference = (PLUGIN_ROOT / "references" / "collaboration-runtime.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("--tmux-wake", ops)
        self.assertIn("--tmux-wake", reference)
        self.assertIn("加入本机联调", reference)
        self.assertIn("get_inbox", reference)
        self.assertIn("短提示", reference)
        self.assertIn("ChatGPT in Chrome", reference)
        self.assertIn("不能证明", reference)

    def test_protocol_starts_from_the_one_step_user_flow(self) -> None:
        text = PROTOCOL.read_text(encoding="utf-8")

        self.assertIn("collab [可选别名]", text)
        self.assertIn("告诉可乐", text)
        self.assertIn("内部注册序列", text)

    def test_repository_validation_runs_the_entry_contract(self) -> None:
        text = VALIDATE.read_text(encoding="utf-8")

        self.assertIn("python3 -B plugins/spec-guard/hooks/test_collab_entry.py", text)

    def test_alias_resolution_stays_agent_driven_and_ambiguity_safe(self) -> None:
        text = self.skill_text()

        self.assertIn("友好别名", text)
        self.assertIn("短随机后缀", text)
        self.assertIn("完整注册名时，直接用 `send_message`", text)
        self.assertIn("`list_agents` 是名称解析步骤", text)
        self.assertIn("只在唯一匹配时发送", text)
        self.assertIn("多个匹配只追问一次最小区别", text)

    def test_unavailable_diagnostic_does_not_promote_sandbox_probe_to_service_verdict(self) -> None:
        text = self.skill_text()

        self.assertIn("MCP 启动错误", text)
        self.assertIn("沙箱内的回环访问或 launchd 探测可能失真", text)
        self.assertIn("不能据此声称后台服务离线", text)
        self.assertIn("优先修复当前宿主的 MCP endpoint 或重开会话", text)

    def test_daily_entry_has_an_explicit_read_only_availability_matrix(self) -> None:
        text = self.skill_text()

        for state_contract in (
            "MCP 工具可用且当前会话尚未注册",
            "MCP 工具可用且当前会话已经注册",
            "运行时状态为 `absent`",
            "宿主侧确认后台服务为 `service-offline`",
            "只给出一条下一步",
        ):
            self.assertIn(state_contract, text)

    def test_human_name_resolution_uses_metadata_without_becoming_a_router(self) -> None:
        text = self.skill_text()
        compact = "".join(text.split())

        self.assertIn("别名、项目简称、宿主和自由工作描述", text)
        self.assertIn("不增加固定匹配 helper", text)
        self.assertIn("不能作为路由、过滤、派单或访问控制", compact)


if __name__ == "__main__":
    unittest.main()
