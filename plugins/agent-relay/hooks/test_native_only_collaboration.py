"""The current collaboration product has one native transport and no XATS fallback."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
HOOKS = ROOT / "plugins" / "spec-guard" / "hooks"


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
            ROOT / "spec" / "collaboration-messaging.md",
            ROOT / "spec" / "host-native-session-routing.md",
            ROOT / "spec" / "authorized-session-delegation.md",
            ROOT / "spec" / "ledger-dependency-lock.md",
            ROOT / "docs" / "optional-features.md",
            ROOT / "plugins" / "spec-guard" / "commands" / "collaboration.md",
            ROOT / "plugins" / "spec-guard" / "skills" / "collab" / "SKILL.md",
            ROOT / "plugins" / "spec-guard" / "skills" / "collaboration-ops" / "SKILL.md",
            ROOT / "plugins" / "spec-guard" / "skills" / "session-delegation" / "SKILL.md",
            ROOT / "plugins" / "spec-guard" / "skills" / "session-routing" / "SKILL.md",
            ROOT / "plugins" / "spec-guard" / "references" / "collaboration-protocol.md",
            ROOT / "plugins" / "spec-guard" / "references" / "collaboration-runtime.md",
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
            ROOT / "docs" / "decisions"
            / "2026-10-04-native-only-collaboration-sunset.md"
        ).read_text(encoding="utf-8")
        self.assertIn("native 成为唯一产品传输", decision)
        self.assertIn("回退演练", decision)
        self.assertIn("不再是退役前置条件", decision)


if __name__ == "__main__":
    unittest.main()
