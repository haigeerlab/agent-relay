#!/usr/bin/env python3
"""Contract tests for bounded session delegation and joined-session display."""
from pathlib import Path
import unittest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DELEGATION = PLUGIN_ROOT / "skills" / "session-delegation" / "SKILL.md"
COLLAB = PLUGIN_ROOT / "skills" / "collab" / "SKILL.md"
OPTIONAL = PLUGIN_ROOT.parents[1] / "docs" / "optional-features.md"
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
            "wake-held", "unreachable", "stale", "unread",
            "recently-active", "online", "未知",
        ):
            self.assertIn(phrase, text)
        self.assertIn("不能仅凭 registered 推断 online", text)
        self.assertIn("不扫描未注册", text)

    def test_name_resolution_never_exposes_or_guesses_full_identity(self):
        text = self.delegation_text() + COLLAB.read_text(encoding="utf-8")
        for phrase in ("同名", "最短区分项", "完整内部 ID", "不能按标题猜"):
            self.assertIn(phrase, text)

    def test_selected_backend_is_reused_without_promoting_native(self):
        text = self.delegation_text()
        self.assertIn("collaboration_backend.py", text)
        self.assertIn("只复用选择器返回的后端", text)
        self.assertIn("不推进 A10 native 转正", text)
        self.assertIn("不删除 XATS", text)

    def test_entry_uses_the_control_surface_without_user_supplied_identity(self):
        text = self.delegation_text()
        for phrase in (
            "session_delegation_control.py", "任务正文只从 stdin 传入",
            "响应丢失后的重试必须复用", "origin session 只由控制器",
            "八小时到期时间", "不初始化运行时",
        ):
            self.assertIn(phrase, text)

    def test_optional_feature_docs_explain_smooth_preapproval_and_limits(self):
        text = OPTIONAL.read_text(encoding="utf-8")
        self.assertIn("跨宿主会话委派", text)
        self.assertIn("项目级 allow", text)
        self.assertIn("同一台 Mac", text)
        self.assertIn("不会自动修改", text)

    def test_repository_validation_runs_the_entry_contract(self):
        validation = VALIDATE.read_text(encoding="utf-8")
        for command in (
            "python3 -B plugins/spec-guard/hooks/test_skill_entrypoints.py",
            "python3 -B plugins/spec-guard/hooks/test_session_delegation_recovery.py",
        ):
            self.assertIn(command, validation)


if __name__ == "__main__":
    unittest.main()
