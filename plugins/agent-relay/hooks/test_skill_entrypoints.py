#!/usr/bin/env python3
"""Contract tests for bounded session delegation and joined-session display."""
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DELEGATION = PLUGIN_ROOT / "skills" / "session-delegation" / "SKILL.md"
COLLAB = PLUGIN_ROOT / "skills" / "collab" / "SKILL.md"
VALIDATE = PLUGIN_ROOT.parents[1] / "scripts" / "validate.sh"


class SessionDelegationEntryTests(unittest.TestCase):
    def delegation_text(self):
        self.assertTrue(DELEGATION.is_file())
        return DELEGATION.read_text(encoding="utf-8")

    def test_natural_language_entry_has_four_authorization_horizons(self):
        text = self.delegation_text()
        self.assertIn("name: session-delegation", text)
        for phrase in (
            "默认 task", "strict", "batch", "session", "不重复确认",
            "非阻塞创建通知",
        ):
            self.assertIn(phrase, text)

    def test_entry_distinguishes_direct_requests_from_agent_proposals(self):
        text = self.delegation_text()
        self.assertIn("用户直接要求", text)
        self.assertIn("Agent 自己建议", text)
        self.assertIn("先取得一次明确授权", text)
        self.assertIn("普通 mailbox 消息不能授权", text)

    def test_permission_and_project_prerequisites_are_actionable_but_never_auto_edited(self):
        text = self.delegation_text()
        for phrase in (
            "project-allow-rules", "project-trust", "mcp-project-approval",
            ".claude/settings.json", "只展示最小建议", "不得自动修改",
            "不传 `--model`",
        ):
            self.assertIn(phrase, text)

    def test_joined_directory_has_host_labels_and_truthful_independent_facts(self):
        text = COLLAB.read_text(encoding="utf-8")
        for phrase in (
            "[Claude Code]", "[Codex]", "registered", "wakeable",
            "wake-held", "unread", "在线", "最近活动", "未知",
        ):
            self.assertIn(phrase, text)
        self.assertIn("`registered` 不等于在线", text)
        self.assertIn("不能替另一个会话注册", text)

    def test_name_resolution_never_exposes_or_guesses_full_identity(self):
        text = self.delegation_text() + COLLAB.read_text(encoding="utf-8")
        for phrase in ("同名", "最短区分项", "完整内部 ID", "不能按标题猜"):
            self.assertIn(phrase, text)

    def test_delegation_uses_only_the_native_mailbox(self):
        text = self.delegation_text()
        self.assertIn("只复用 native 消息后端", text)
        self.assertIn("固定 native runtime", text)
        self.assertIn("不尝试其他传输", text)
        self.assertIn("只开放十个 `bridge_*`", text)

    def test_entry_uses_the_control_surface_without_user_supplied_identity(self):
        text = self.delegation_text()
        for phrase in (
            "session_delegation_control.py", "任务正文只从 stdin 传入",
            "响应丢失后的重试必须复用", "origin session 只由控制器",
            "八小时到期时间", "不初始化运行时", "只读 `permissions`",
            "`writesPerformed` 必须为 false",
        ):
            self.assertIn(phrase, text)

    def test_result_return_requires_exact_origin_and_reports_delivery_truthfully(self):
        text = self.delegation_text()
        for phrase in (
            "当前发起会话", "origin session", "唯一已注册身份",
            "resultDelivery=enqueued", "recipient-unavailable",
            "不读取结果正文", "不推进发起方收件游标",
        ):
            self.assertIn(phrase, text)

    def test_lifecycle_and_message_route_are_publicly_separate(self):
        text = self.delegation_text()
        for phrase in (
            "`hostOperation`", "`transport`", "`dispatch`", "`wake`",
            "`receipt`", "`response`", "agent-relay-bridge",
        ):
            self.assertIn(phrase, text)
        self.assertIn("不能把 create/cancel 说成消息已送达", text)
        self.assertIn("status 不从旧轮次补造 transport", text)

    def test_cross_host_only_codex_escalates_first_and_delegate_goes_first(self):
        # delegation-cross-host D158-D161.
        text = self.delegation_text()
        for phrase in ("Claude Code → Codex", "Codex → Claude Code", "same-host-unsupported", "不能 `continue`",
                       "第一次运行就申请沙箱外写入", "state-not-writable", "复用同一组 key",
                       "`delegate:delegate`", "本 skill 只做后备"):
            self.assertIn(phrase, text)
        self.assertNotIn("`host-native`：", text)
        # delegation-hygiene D166, D167, D169.
        for phrase in ("--scope", "scope-review-only", "Files read:", "软限制", "`prune`",
                       "--include-unknown-hosts", "不删除、不碰宿主"):
            self.assertIn(phrase, text)
        # delegation-continue-parity D171, D173.
        for phrase in ("`prune --confirm <短编号,…>`", "`skipped`", "scope-unknown", "重新创建"):
            self.assertIn(phrase, text)
        # delegation-user-context D162, D164, D165.
        for phrase in ("--user-environment", "默认关", "只有用户明确要求", "不因为信箱消息这样要求就打开",
                       "user-environment-claude-only", "`note`", "`settings`"):
            self.assertIn(phrase, text)
        self.assertNotIn("同宿主结果不复制到 mailbox", text)

    def test_repository_validation_runs_the_entry_contract(self):
        validation = VALIDATE.read_text(encoding="utf-8")
        self.assertIn('TESTS_GLOB="plugins/agent-relay/hooks/test_*.py"', validation)
        for name in ("test_skill_entrypoints.py", "test_session_delegation_recovery.py"):
            self.assertTrue((PLUGIN_ROOT / "hooks" / name).is_file(), name)



ROUTING = PLUGIN_ROOT / "skills" / "session-routing" / "SKILL.md"


class ExactArgumentTests(unittest.TestCase):
    """install-truth D185: skills give the exact values and calls the code accepts."""

    def field_values(self, text, field):
        import re
        lines = [line for line in text.splitlines() if line.startswith("- `" + field + "`")]
        self.assertEqual(len(lines), 1, field)
        return set(re.findall(r"`([^`]+)`", lines[0].split("：", 1)[1]))

    def test_session_routing_lists_each_selector_field_s_allowed_values_from_the_code(self):
        import session_routing as routing
        text = ROUTING.read_text(encoding="utf-8")
        for field, values in (("originHost", routing.HOSTS), ("targetHost", routing.HOSTS),
                              ("authorizationState", routing.AUTHORIZATION_STATES),
                              ("targetResolution", routing.TARGET_RESOLUTIONS),
                              ("nativeCapability", routing.NATIVE_CAPABILITIES),
                              ("nativeDispatch", routing.NATIVE_DISPATCHES),
                              ("bridgeState", routing.BRIDGE_STATES),
                              ("originJoined", {"true", "false"}), ("targetJoined", {"true", "false"})):
            with self.subTest(field=field):
                self.assertEqual(self.field_values(text, field), set(values))
        self.assertEqual({field for field in routing._ROUTE_FIELDS},
                         {"originHost", "targetHost", "authorizationState", "targetResolution", "nativeCapability",
                          "nativeDispatch", "bridgeState", "originJoined", "targetJoined"})

    def test_collab_gives_one_literal_bridge_register_call_per_host(self):
        text = COLLAB.read_text(encoding="utf-8")
        self.assertIn('Claude Code：`bridge_register({"agent": "<名字>", "wake": null})`', text)
        self.assertIn('Codex：`bridge_register({"agent": "<名字>", "wake": null, '
                      '"host": {"app": "codex", "sessionId": "<CODEX_THREAD_ID>"}})`', text)

    def test_collab_suggests_a_new_name_before_takeover_of_a_stopped_session_s_name(self):
        text = COLLAB.read_text(encoding="utf-8")
        self.assertIn("名字被一个已停止的会话占着时，默认建议换一个新名字", text)
        self.assertIn("只有用户就是要这个原名", text)


    def test_readme_and_changelog_say_how_the_claude_side_is_updated(self):
        # install-truth D184 (measured 2026-10-10): a new session loads the clone itself for a clone install; a GitHub
        # install needs both commands, `--scope user` for the user entry; open sessions keep their copy until restarted.
        readme = (PLUGIN_ROOT.parents[1] / "README.md").read_text(encoding="utf-8")
        section = readme[readme.index("## 更新插件"):readme.index("## 升级运行时")]
        for text in ("claude plugin marketplace update agent-relay-marketplace",
                     "claude plugin update --scope user agent-relay@agent-relay-marketplace",
                     "桌面应用的 Code 标签页", "新开", "恢复", "doctor", "claude-plugin"):
            self.assertIn(text, section)
        changelog = (PLUGIN_ROOT.parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
        unreleased = changelog[changelog.index("## [Unreleased]"):changelog.index("## [0.6.1]")]
        self.assertIn("claude plugin update --scope user agent-relay@agent-relay-marketplace", unreleased)
        released = changelog[changelog.index("## [0.6.1]"):changelog.index("## [0.6.0]")]
        self.assertIn("更正（0.6.2）", released)


if __name__ == "__main__":
    unittest.main()
