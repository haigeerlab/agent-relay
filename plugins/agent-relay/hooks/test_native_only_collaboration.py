"""The current collaboration product has one native transport and no XATS fallback."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins" / "agent-relay"
HOOKS = PLUGIN / "hooks"
HISTORY = ROOT / "docs" / "history" / "spec-guard"


class NativeOnlyCollaborationTests(unittest.TestCase):
    def test_retired_xats_product_files_are_absent(self):
        retired = (
            "collaboration_runtime.py",
            "collaboration_adapters.py",
            "collaboration_auth_header.py",
            "collaboration_claude.py",
            "collaboration_claude_stdio.py",
            "collaboration_backend.py",
            "native_collaboration_activate.py",
            "native_collaboration_archive.py",
            "native_collaboration_cutover.py",
            "native_collaboration_rollback.py",
        )
        self.assertEqual(
            [name for name in retired if (HOOKS / name).exists()],
            [],
            "retired XATS product files must not remain callable",
        )

    def test_current_entry_contracts_do_not_offer_xats(self):
        current = (
            HISTORY / "spec" / "collaboration-messaging.md",
            HISTORY / "spec" / "host-native-session-routing.md",
            HISTORY / "spec" / "authorized-session-delegation.md",
            PLUGIN / "commands" / "collaboration.md",
            PLUGIN / "skills" / "collab" / "SKILL.md",
            PLUGIN / "skills" / "collaboration-ops" / "SKILL.md",
            PLUGIN / "skills" / "session-delegation" / "SKILL.md",
            PLUGIN / "skills" / "session-routing" / "SKILL.md",
            PLUGIN / "references" / "collaboration-protocol.md",
            PLUGIN / "references" / "collaboration-runtime.md",
            HOOKS / "native_collaboration_runtime.py",
            HOOKS / "session_delegation_backend.py",
            HOOKS / "session_delegation_claude.py",
            HOOKS / "session_delegation_codex.py",
            HOOKS / "session_delegation_control.py",
        )
        offenders = []
        for path in current:
            text = path.read_text(encoding="utf-8").lower()
            if "xats" in text or "cross-agent-teams" in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_current_decision_declares_native_only_without_a_rollback_gate(self):
        decision = (
            HISTORY / "docs" / "decisions"
            / "2026-10-04-native-only-collaboration-sunset.md"
        ).read_text(encoding="utf-8")
        self.assertIn("native 成为唯一产品传输", decision)
        self.assertIn("回退演练", decision)
        self.assertIn("不再是退役前置条件", decision)


if __name__ == "__main__":
    unittest.main()
