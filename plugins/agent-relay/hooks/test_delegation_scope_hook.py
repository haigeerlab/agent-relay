#!/usr/bin/env python3
"""delegation-hygiene D167: the PreToolUse hook that keeps a scoped Claude Code review inside its scope."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().with_name("delegation_scope_hook.py")


class ScopeHookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ar-scope-hook-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project"
        (self.root / "docs").mkdir(parents=True)
        (self.root / "README.md").write_text("readme", encoding="utf-8")
        (self.root / "docs" / "guide.md").write_text("guide", encoding="utf-8")
        (self.root / "other.txt").write_text("secret", encoding="utf-8")
        (self.root / "docs" / "escape.md").symlink_to(self.root / "other.txt")

    def decide(self, event, scope=("README.md", "docs")):
        argv = [sys.executable, "-B", str(HOOK), "--root", str(self.root)]
        for item in scope:
            argv += ["--scope", item]
        data = event if isinstance(event, str) else json.dumps(event)
        done = subprocess.run(argv, input=data, capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        if not done.stdout.strip():
            return "allow"
        output = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecisionReason"], "outside the review scope")
        return output["permissionDecision"]

    def event(self, tool, **tool_input):
        return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(self.root)}

    def test_inside_the_scope_is_allowed(self):
        self.assertEqual(self.decide(self.event("Read", file_path=str(self.root / "README.md"))), "allow")
        self.assertEqual(self.decide(self.event("Read", file_path="docs/guide.md")), "allow")
        self.assertEqual(self.decide(self.event("Grep", pattern="x", path=str(self.root / "docs"))), "allow")
        self.assertEqual(self.decide(self.event("Glob", pattern="*.md", path="docs")), "allow")

    def test_outside_the_scope_is_denied(self):
        for event in (self.event("Read", file_path=str(self.root / "other.txt")),
                      self.event("Read", file_path=str(self.root / ".gitignore")),
                      self.event("Read", file_path=os.path.expanduser("~/.claude/settings.json")),
                      self.event("Read", file_path=str(self.root / "docs" / "escape.md")),
                      self.event("Grep", pattern="secret"),
                      self.event("Glob", pattern="**/*"),
                      self.event("Glob", pattern=str(self.root.parent) + "/**/*.md"),
                      self.event("Grep", pattern="x", path=str(self.root.parent))):
            with self.subTest(event=event["tool_input"]):
                self.assertEqual(self.decide(event), "deny")

    def test_a_scope_of_the_project_root_allows_project_wide_search(self):
        self.assertEqual(self.decide(self.event("Grep", pattern="x"), scope=(".",)), "allow")
        self.assertEqual(self.decide(self.event("Read", file_path=str(self.root.parent / "x")), scope=(".",)), "deny")

    def test_malformed_input_and_other_tools(self):
        self.assertEqual(self.decide("not json"), "deny")
        self.assertEqual(self.decide({"tool_name": "Read", "tool_input": "x"}), "deny")
        self.assertEqual(self.decide(self.event("Read")), "deny")
        self.assertEqual(self.decide(self.event("mcp__agent-relay__bridge_send", to="x")), "allow",
                         "only file tools are scoped")


if __name__ == "__main__":
    unittest.main()
