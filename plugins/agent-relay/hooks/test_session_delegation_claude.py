"""Claude Code background adapter tests; never inspect real sessions or settings."""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
import tempfile
import unittest

from collaboration_adapters import MCP_SERVER_NAME
from session_delegation import AuthorizationRequest, DelegationStore
from session_delegation_codex import XATS_COMMUNICATION_TOOLS
from session_delegation_claude import (
    CLAUDE_COMMUNICATION_RULES,
    COMMUNICATION_TOOLS,
    ClaudeAdapter,
    ClaudeAdapterError,
    ClaudeCommandUncertain,
    ClaudeInstallation,
    _bounded_prompt,
    build_create_command,
    communication_rules,
    discover_claude,
    inspect_project_permissions,
    required_project_allow,
    sanitized_environment,
)


NOW = 1_800_000_000


class ScriptedRunner:
    def __init__(self, results):
        self.results = deque(results)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        result = self.results.popleft()
        if isinstance(result, Exception):
            raise result
        return result


def completed(stdout="", stderr="", returncode=0):
    return CompletedProcess([], returncode, stdout, stderr)


class InstallationAndPermissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sg-claude-adapter-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        (self.project / ".claude").mkdir(parents=True)

    def write_permissions(self, allow, deny=()):
        path = self.project / ".claude" / "settings.json"
        path.write_text(json.dumps({
            "permissions": {"allow": list(allow), "deny": list(deny)},
        }), encoding="utf-8")
        return path

    def test_discovers_exact_supported_binary_and_rejects_an_old_version(self):
        binary = self.root / "claude"
        binary.write_text("fake", encoding="utf-8")
        binary.chmod(0o700)
        runner = ScriptedRunner([completed("2.1.288 (Claude Code)\n")])
        found = discover_claude(binary, run=runner)
        self.assertEqual(found.binary, binary.resolve())
        self.assertEqual(found.version, "2.1.288")
        self.assertEqual(runner.calls[0][0], [str(binary.resolve()), "--version"])

        with self.assertRaisesRegex(ClaudeAdapterError, "unsupported-version"):
            discover_claude(
                binary,
                run=ScriptedRunner([completed("2.1.200 (Claude Code)\n")]),
            )

    def test_project_permissions_can_preapprove_two_turns_without_rewriting_settings(self):
        path = self.write_permissions(CLAUDE_COMMUNICATION_RULES)
        before = path.read_bytes()
        readiness = inspect_project_permissions(self.project, "safe-review", None)
        self.assertTrue(readiness.ready)
        self.assertEqual(readiness.permission_mode, "dontAsk")
        self.assertEqual(path.read_bytes(), before)

    def test_missing_allow_or_matching_deny_is_a_diagnostic_prerequisite(self):
        self.write_permissions(("Read", "Grep", "Glob"))
        missing = inspect_project_permissions(self.project, "safe-review", None)
        self.assertFalse(missing.ready)
        self.assertEqual(missing.prerequisite, "project-allow-rules")

        self.write_permissions(
            (*CLAUDE_COMMUNICATION_RULES, "Read", "Grep", "Glob"),
            ("mcp__spec-guard-collaboration__*",),
        )
        denied = inspect_project_permissions(self.project, "safe-review", None)
        self.assertFalse(denied.ready)
        self.assertEqual(denied.prerequisite, "project-deny-rules")

    def test_create_command_is_bounded_and_omits_model_and_permission_bypass(self):
        installation = ClaudeInstallation(Path("/opt/claude"), "2.1.288")
        command = build_create_command(
            installation,
            Path("/private/tmp/session.mcp.json"),
            "spec-guard-12345678",
            "Review the diff",
            "safe-review",
            "dontAsk",
        )
        joined = " ".join(command)
        self.assertIn("--background", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertIn("--setting-sources", command)
        self.assertIn("project,local", command)
        self.assertIn("--permission-prompts", command)
        self.assertIn("none", command)
        self.assertIn("--no-chrome", command)
        self.assertNotIn("--model", command)
        self.assertNotIn("--session-id", command)
        self.assertNotIn("dangerously", joined)
        tools = command[command.index("--tools") + 1]
        self.assertIn("Read", tools)
        self.assertNotIn("Edit", tools)
        self.assertEqual(command[-2:], ("--", "Review the diff"))

    def test_native_backend_uses_its_own_exact_tool_names_and_project_allow_rules(self):
        server_name = "spec-guard-native-collaboration"
        rules = communication_rules(server_name)
        self.write_permissions(rules)
        readiness = inspect_project_permissions(
            self.project, "safe-review", None, server_name=server_name,
        )
        self.assertTrue(readiness.ready)
        command = build_create_command(
            ClaudeInstallation(Path("/opt/claude"), "2.1.288"),
            Path("/private/tmp/session.mcp.json"),
            "spec-guard-12345678", "Review", "safe-review", "dontAsk",
            server_name=server_name,
        )
        tools = command[command.index("--tools") + 1]
        self.assertIn("mcp__spec-guard-native-collaboration__bridge_register", tools)
        self.assertNotIn("mcp__spec-guard-collaboration__bridge_register", tools)

    def test_xats_backend_uses_register_agent_names_not_native_bridge_names(self):
        rules = communication_rules(MCP_SERVER_NAME, XATS_COMMUNICATION_TOOLS)
        self.write_permissions(rules)
        readiness = inspect_project_permissions(
            self.project, "safe-review", None,
            communication_tools=XATS_COMMUNICATION_TOOLS,
        )
        self.assertTrue(readiness.ready)
        command = build_create_command(
            ClaudeInstallation(Path("/opt/claude"), "2.1.288"),
            Path("/private/tmp/session.mcp.json"),
            "spec-guard-12345678", "Review", "safe-review", "dontAsk",
            communication_tools=XATS_COMMUNICATION_TOOLS,
        )
        tools = command[command.index("--tools") + 1]
        self.assertIn("mcp__spec-guard-collaboration__register_agent", tools)
        self.assertNotIn("bridge_register", tools)

        prompt = _bounded_prompt(
            "Review", "12345678-1234-1234-1234-123456789abc", "review",
            XATS_COMMUNICATION_TOOLS, "safe-review",
        )
        self.assertIn("Call register_agent exactly once", prompt)
        self.assertIn("ui_pid", prompt)
        self.assertNotIn("bridge_register", prompt)

    def test_native_registration_does_not_bind_general_wake_for_write_permission(self):
        prompt = _bounded_prompt(
            "Implement", "12345678-1234-1234-1234-123456789abc", "dev",
            COMMUNICATION_TOOLS, "bounded-development",
        )
        self.assertIn("Call bridge_register exactly once", prompt)
        self.assertIn("wake null", prompt)
        with self.assertRaisesRegex(ClaudeAdapterError, "communication-tools-invalid"):
            communication_rules("unsafe", ("ask_codex",))

    def test_permission_preflight_rules_include_only_prompting_tools(self):
        review = required_project_allow(
            "safe-review", None, communication_tools=XATS_COMMUNICATION_TOOLS)
        self.assertEqual(review, communication_rules(
            MCP_SERVER_NAME, XATS_COMMUNICATION_TOOLS))
        development = required_project_allow(
            "bounded-development", None,
            communication_tools=XATS_COMMUNICATION_TOOLS,
        )
        self.assertEqual(development[-3:], ("Edit", "Write", "Bash"))
        self.assertNotIn("Read", development)

    def test_environment_strips_both_hosts_session_identity_and_bridge_token(self):
        environment = sanitized_environment({
            "PATH": "/bin", "CODEX_THREAD_ID": "codex",
            "CODEX_SESSION_ID": "codex-session",
            "CLAUDE_CODE_SESSION_ID": "claude",
            "SPEC_GUARD_COLLABORATION_TOKEN": "secret",
        })
        self.assertEqual(environment, {"PATH": "/bin"})


class AdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sg-claude-flow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        (self.project / ".claude").mkdir(parents=True)
        (self.project / ".claude" / "settings.json").write_text(json.dumps({
            "permissions": {"allow": [
                *CLAUDE_COMMUNICATION_RULES, "Read", "Grep", "Glob",
                "Edit", "Write", "Bash(git *)",
            ], "deny": []},
        }), encoding="utf-8")
        self.store = DelegationStore(self.root / "state", now=lambda: NOW)
        self.installation = ClaudeInstallation(self.root / "claude", "2.1.288")
        self.installation.binary.write_text("fake", encoding="utf-8")
        self.installation.binary.chmod(0o700)
        self.config = self.root / "state" / "claude-test.mcp.json"
        self.config.write_text('{"mcpServers":{}}\n', encoding="utf-8")
        self.config.chmod(0o600)
        self.envelope, self.claim = self.make_claim()

    def make_claim(self, *, permission="safe-review", dirty=False, key="claude-request-123"):
        request = AuthorizationRequest(
            authority="direct-user", horizon="task", origin_host="codex",
            origin_session="origin-session", project_root=self.project,
            repo_identity="git:example/project", baseline="a" * 40, dirty=dirty,
            target_hosts=("claude",), permission_intent=permission,
            host_permission=None, max_sessions=1, expires_at=NOW + 600, depth=0,
            idempotency_key=key, summary="Review current diff",
        )
        envelope = self.store.authorize(request)
        claim = self.store.claim_launch(
            envelope.envelope_id, key + "-launch", "claude", self.project,
            "a" * 40, permission,
        )
        return envelope, claim

    def entry(self, *, short_id="ce5b9501", state="done", status="idle"):
        return {
            "id": short_id,
            "sessionId": "ce5b9501-0817-479d-886e-772bafbbee6f",
            "name": "spec-guard-" + self.claim.delegation_id[:8],
            "cwd": str(self.project.resolve()),
            "kind": "background", "pid": 123, "state": state, "status": status,
            "startedAt": "2026-10-03T00:00:00Z",
        }

    def runner_for_create(self, entry=None):
        entry = self.entry() if entry is None else entry
        return ScriptedRunner([
            completed("Starting background service…\nbackgrounded · ce5b9501 · test\n"),
            completed(json.dumps([entry])),
        ])

    def adapter(self, runner, *, wake=None, registration_probe=None):
        return ClaudeAdapter(
            self.store,
            self.installation,
            self.root,
            runner=runner,
            config_factory=lambda _delegation_id: self.config,
            native_wake=wake,
            registration_probe=registration_probe,
            now=lambda: NOW,
        )

    def complete_claim(self):
        runner = self.runner_for_create()
        result = self.adapter(runner).create(self.claim.delegation_id, "Review")
        self.store.set_turn_ref(self.claim.delegation_id, result.host_session_ref)
        self.store.advance(self.claim.delegation_id, "registered", "host-registered")
        self.store.advance(self.claim.delegation_id, "running", "host-running")
        self.store.advance(self.claim.delegation_id, "completed", "host-completed")
        return result

    def test_create_binds_only_the_exact_cli_id_and_full_session_id(self):
        runner = self.runner_for_create()
        result = self.adapter(runner).create(self.claim.delegation_id, "Review")
        self.assertEqual(result.state, "created")
        self.assertEqual(result.host_ref, "ce5b9501")
        self.assertEqual(result.host_session_ref,
                         "ce5b9501-0817-479d-886e-772bafbbee6f")
        stored = self.store.get_delegation(self.claim.delegation_id)
        self.assertEqual(stored.host_ref, "ce5b9501")
        self.assertEqual(stored.host_session_ref, result.host_session_ref)
        create_command = runner.calls[0][0]
        self.assertNotIn("--model", create_command)
        for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
            self.assertNotIn(name, runner.calls[0][1]["env"])

    def test_response_loss_reconciles_only_an_observed_exact_id(self):
        uncertain = ClaudeCommandUncertain(
            "claude-background",
            "backgrounded · ce5b9501 · test\n",
        )
        runner = ScriptedRunner([
            uncertain,
            completed(json.dumps([self.entry()])),
        ])
        result = self.adapter(runner).create(self.claim.delegation_id, "Review")
        self.assertEqual(result.state, "created")
        self.assertEqual(result.host_ref, "ce5b9501")

    def test_status_requires_exact_registration_before_completing_initial_turn(self):
        self.adapter(self.runner_for_create()).create(
            self.claim.delegation_id, "Review")
        expected_name = "Claude Code session-" + self.claim.delegation_id[:8]
        seen = []
        adapter = self.adapter(
            ScriptedRunner([completed(json.dumps([self.entry()]))]),
            registration_probe=lambda name, pid, session, intent: (
                seen.append((name, pid, session, intent)) or True),
        )
        result = adapter.status(self.claim.delegation_id)
        self.assertEqual(result.state, "completed")
        self.assertEqual(seen, [(
            expected_name, 123, "ce5b9501-0817-479d-886e-772bafbbee6f",
            "safe-review",
        )])
        self.assertEqual(
            self.store.get_delegation(self.claim.delegation_id).state, "completed")

    def test_status_holds_when_exact_mailbox_registration_is_missing(self):
        self.adapter(self.runner_for_create()).create(
            self.claim.delegation_id, "Review")
        adapter = self.adapter(
            ScriptedRunner([completed(json.dumps([self.entry()]))]),
            registration_probe=lambda _name, _pid, _session, _intent: False,
        )
        result = adapter.status(self.claim.delegation_id)
        self.assertEqual(result.state, "created")
        self.assertEqual(result.prerequisite, "mailbox-registration-missing")

    def test_response_loss_without_exact_id_never_guesses_from_name_or_project(self):
        runner = ScriptedRunner([
            ClaudeCommandUncertain("claude-background", "Starting background service…\n"),
        ])
        result = self.adapter(runner).create(self.claim.delegation_id, "Review")
        self.assertEqual(result.state, "unknown")
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state, "unknown")

    def test_trust_and_mcp_approval_failures_are_held_without_editing_project_settings(self):
        settings = self.project / ".claude" / "settings.json"
        before = settings.read_bytes()
        for stderr, prerequisite in (
            ("Workspace trust is required", "project-trust"),
            ("MCP server approval is required", "mcp-project-approval"),
        ):
            with self.subTest(prerequisite=prerequisite):
                envelope, claim = self.make_claim(key="held-" + prerequisite)
                result = self.adapter(ScriptedRunner([
                    completed(stderr=stderr, returncode=1),
                ])).create(claim.delegation_id, "Review")
                self.assertEqual(result.state, "held")
                self.assertEqual(result.prerequisite, prerequisite)
                self.assertEqual(self.store.get_delegation(claim.delegation_id).state,
                                 "creating")
        self.assertEqual(settings.read_bytes(), before)

    def test_bounded_development_requires_clean_isolated_worktree(self):
        _envelope, claim = self.make_claim(
            permission="bounded-development", key="claude-development-123")
        with self.assertRaisesRegex(ClaudeAdapterError, "isolated-clean-worktree-required"):
            self.adapter(ScriptedRunner([])).create(claim.delegation_id, "Implement")

        runner = self.runner_for_create()
        result = self.adapter(runner).create(
            claim.delegation_id, "Implement", isolated_worktree=True,
        )
        self.assertEqual(result.state, "created")
        tools = runner.calls[0][0][runner.calls[0][0].index("--tools") + 1]
        self.assertIn("Edit", tools)
        self.assertIn("Bash", tools)

    def test_active_follow_up_uses_native_wake_and_never_invokes_cli_resume(self):
        self.complete_claim()
        wake_calls = []
        runner = ScriptedRunner([completed(json.dumps([self.entry()]))])
        adapter = self.adapter(
            runner,
            wake=lambda session_ref, prompt: wake_calls.append((session_ref, prompt))
            or "claude-native-turn-2",
        )
        result = adapter.continue_turn(self.claim.delegation_id, "Check again")
        self.assertEqual(result.state, "running")
        self.assertEqual(wake_calls, [(
            "ce5b9501-0817-479d-886e-772bafbbee6f", "Check again",
        )])
        self.assertFalse(any("--resume" in command for command, _ in runner.calls))

    def test_idle_follow_up_without_wake_stops_then_resumes_the_exact_session(self):
        self.complete_claim()
        runner = ScriptedRunner([
            completed(json.dumps([self.entry()])),
            completed("stopped ce5b9501\n"),
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ])
        result = self.adapter(runner).continue_turn(
            self.claim.delegation_id, "Check again")
        self.assertEqual(result.state, "running")
        self.assertEqual(runner.calls[1][0], [
            str(self.installation.binary), "stop", "ce5b9501",
        ])
        self.assertEqual(runner.calls[2][0][:4], [
            str(self.installation.binary), "--background", "--resume",
            "ce5b9501-0817-479d-886e-772bafbbee6f",
        ])

    def test_blocked_idle_follow_up_uses_the_same_exact_resume_path(self):
        self.complete_claim()
        runner = ScriptedRunner([
            completed(json.dumps([
                self.entry(state="blocked", status="idle"),
            ])),
            completed("stopped ce5b9501\n"),
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([
                self.entry(state="running", status="working"),
            ])),
        ])

        result = self.adapter(runner).continue_turn(
            self.claim.delegation_id, "Check again")

        self.assertEqual(result.state, "running")
        self.assertEqual(runner.calls[2][0][:4], [
            str(self.installation.binary), "--background", "--resume",
            "ce5b9501-0817-479d-886e-772bafbbee6f",
        ])

    def test_idle_stop_uncertainty_never_attempts_resume_or_creates_a_copy(self):
        self.complete_claim()
        runner = ScriptedRunner([
            completed(json.dumps([self.entry()])),
            ClaudeCommandUncertain("claude-stop"),
        ])
        result = self.adapter(runner).continue_turn(
            self.claim.delegation_id, "Check again")
        self.assertEqual(result.state, "unknown")
        self.assertFalse(any("--resume" in command for command, _ in runner.calls))

    def test_stopped_follow_up_uses_full_session_id_and_no_startup_overrides(self):
        self.complete_claim()
        stopped = self.entry(state="stopped", status="stopped")
        runner = ScriptedRunner([
            completed(json.dumps([stopped])),
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ])
        result = self.adapter(runner).continue_turn(
            self.claim.delegation_id, "Check again")
        self.assertEqual(result.state, "running")
        resume = runner.calls[1][0]
        self.assertEqual(resume[:4], [
            str(self.installation.binary), "--background", "--resume",
            "ce5b9501-0817-479d-886e-772bafbbee6f",
        ])
        for forbidden in (
            "--name", "--mcp-config", "--permission-mode", "--tools", "--model",
        ):
            self.assertNotIn(forbidden, resume)

    def test_busy_active_session_is_held_instead_of_copied(self):
        self.complete_claim()
        busy = self.entry(state="running", status="working")
        result = self.adapter(ScriptedRunner([
            completed(json.dumps([busy])),
        ])).continue_turn(self.claim.delegation_id, "Do not copy")
        self.assertEqual(result.state, "held")
        self.assertEqual(result.prerequisite, "target-busy")

    def test_cancel_confirms_exact_stop_before_marking_cancelled_and_is_retryable(self):
        self.complete_claim()
        managed = self.store.root / (
            "claude-" + self.claim.delegation_id + ".mcp.json")
        managed.write_text('{"mcpServers":{}}\n', encoding="utf-8")
        managed.chmod(0o600)
        runner = ScriptedRunner([
            completed("stopped ce5b9501\n"),
        ])
        result = self.adapter(runner).cancel(self.claim.delegation_id)
        self.assertEqual(result.state, "cancelled")
        self.assertEqual(runner.calls[0][0], [
            str(self.installation.binary), "stop", "ce5b9501",
        ])
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state,
                         "cancelled")
        self.assertFalse(managed.exists())

    def test_status_accepts_post_stop_done_entry_without_status_or_pid(self):
        self.complete_claim()
        self.adapter(ScriptedRunner([
            completed("stopped ce5b9501\n"),
        ])).cancel(self.claim.delegation_id)
        terminal = self.entry(state="done", status=None)
        terminal["pid"] = None

        result = self.adapter(ScriptedRunner([
            completed(json.dumps([terminal])),
        ])).status(self.claim.delegation_id)

        self.assertEqual(result.state, "cancelled")
        self.assertEqual(result.host_status, "done")

    def test_stop_failure_does_not_claim_the_host_stopped(self):
        self.complete_claim()
        runner = ScriptedRunner([
            completed(stderr="busy", returncode=1),
            completed("stopped ce5b9501\n"),
        ])
        adapter = self.adapter(runner)
        result = adapter.cancel(self.claim.delegation_id)
        self.assertEqual(result.state, "unknown")
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state,
                         "unknown")
        retried = adapter.cancel(self.claim.delegation_id)
        self.assertEqual(retried.state, "cancelled")
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state,
                         "cancelled")


if __name__ == "__main__":
    unittest.main()
