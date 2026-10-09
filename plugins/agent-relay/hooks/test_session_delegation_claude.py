"""Claude Code background adapter tests; never inspect real sessions or settings."""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
import tempfile
import unittest

from session_delegation import AuthorizationRequest, DelegationStore
from session_delegation_claude import (
    CLAUDE_COMMUNICATION_RULES,
    COMMUNICATION_TOOLS,
    ClaudeAdapter,
    ClaudeAdapterError,
    ClaudeCommandUncertain,
    ClaudeInstallation,
    _bounded_prompt,
    build_create_command,
    build_resume_command,
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


class RepeatingRunner(ScriptedRunner):
    """Like ScriptedRunner, but the last result answers every later call."""

    def __call__(self, command, **kwargs):
        if len(self.results) == 1:
            self.calls.append((list(command), kwargs))
            return self.results[0]
        return super().__call__(command, **kwargs)


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
            ("mcp__agent-relay__*",),
        )
        denied = inspect_project_permissions(self.project, "safe-review", None)
        self.assertFalse(denied.ready)
        self.assertEqual(denied.prerequisite, "project-deny-rules")

    def test_create_command_is_bounded_and_omits_model_and_permission_bypass(self):
        installation = ClaudeInstallation(Path("/opt/claude"), "2.1.288")
        command = build_create_command(
            installation,
            Path("/private/tmp/session.mcp.json"),
            "agent-relay-12345678",
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

    def test_the_user_environment_changes_only_sources_skills_and_the_skill_tool(self):
        # delegation-user-context D163: the default launch is unchanged; the option loads the user layer and skills.
        installation = ClaudeInstallation(Path("/opt/claude"), "2.1.295")
        args = (installation, Path("/private/tmp/session.mcp.json"), "agent-relay-12345678", "Review", "safe-review",
                "dontAsk")
        default = build_create_command(*args)
        tools = ",".join(("Read", "Grep", "Glob", *communication_rules("agent-relay")))
        self.assertEqual(default, (
            "/opt/claude", "--background", "--name", "agent-relay-12345678",
            "--mcp-config", "/private/tmp/session.mcp.json", "--strict-mcp-config",
            "--setting-sources", "project,local", "--permission-mode", "dontAsk",
            "--permission-prompts", "none", "--disable-slash-commands", "--no-chrome",
            "--tools", tools, "--", "Review"))
        user = build_create_command(*args, "user-environment")
        expected = list(default)
        expected[expected.index("project,local")] = "user,project,local"
        expected.remove("--disable-slash-commands")
        expected[expected.index(tools)] = tools + ",Skill"
        self.assertEqual(user, tuple(expected))
        development = build_create_command(installation, Path("/private/tmp/s.json"), "n", "Implement",
                                           "bounded-development", "dontAsk", "user-environment")
        self.assertIn("Skill", development[development.index("--tools") + 1].split(","))
        self.assertIn("Edit", development[development.index("--tools") + 1].split(","))

    def test_the_preflight_reads_what_the_session_will_load(self):
        # delegation-user-context D164: the user layer counts only with the option; its deny too.
        from unittest import mock
        from session_delegation_claude import GLOBAL_ALLOW_NOTE, settings_sources
        config = self.root / "claude-config"
        config.mkdir()
        user_settings = config / "settings.json"
        rules = (*communication_rules("agent-relay"), "Skill")
        user_settings.write_text(json.dumps({"permissions": {"allow": list(rules)}}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(config)}):
            default = inspect_project_permissions(self.project, "safe-review", None, server_name="agent-relay")
            self.assertFalse(default.ready)
            self.assertEqual(default.prerequisite, "project-allow-rules")
            user = inspect_project_permissions(self.project, "safe-review", "user-environment",
                                               server_name="agent-relay")
            self.assertTrue(user.ready, user)
            self.assertIn("Skill", required_project_allow("safe-review", "user-environment",
                                                          server_name="agent-relay"))
            self.assertNotIn("Skill", required_project_allow("safe-review", None, server_name="agent-relay"))
            self.assertEqual(settings_sources(None), [".claude/settings.local.json", ".claude/settings.json"])
            self.assertEqual(settings_sources("user-environment"),
                             [".claude/settings.local.json", ".claude/settings.json", str(user_settings)])
            self.assertIn("~/.claude/settings.json does not apply to a default delegated session", GLOBAL_ALLOW_NOTE)

            user_settings.write_text(json.dumps({"permissions": {"allow": list(rules), "deny": ["Read"]}}),
                                     encoding="utf-8")
            self.write_permissions(rules)
            self.assertTrue(inspect_project_permissions(self.project, "safe-review", None,
                                                        server_name="agent-relay").ready, "the user deny is not read")
            blocked = inspect_project_permissions(self.project, "safe-review", "user-environment",
                                                  server_name="agent-relay")
            self.assertEqual((blocked.ready, blocked.prerequisite), (False, "project-deny-rules"))

    def test_a_scoped_review_launch_carries_the_scope_hook(self):
        # delegation-hygiene D167: one --settings with the PreToolUse hook; nothing else moves.
        import shlex
        installation = ClaudeInstallation(Path("/opt/claude"), "2.1.295")
        args = (installation, Path("/private/tmp/session.mcp.json"), "agent-relay-12345678", "Review", "safe-review",
                "dontAsk")
        plain = build_create_command(*args)
        scoped = build_create_command(*args, scope=("README.md", "docs"), scope_root=self.project)
        self.assertEqual(scoped.count("--settings"), 1)
        index = scoped.index("--settings")
        self.assertEqual(scoped[:index] + scoped[index + 2:], plain)
        hooks = json.loads(scoped[index + 1])["hooks"]["PreToolUse"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["matcher"], "Read|Grep|Glob")
        command = shlex.split(hooks[0]["hooks"][0]["command"])
        self.assertTrue(command[-7].endswith("delegation_scope_hook.py"), command)
        self.assertEqual(command[-6:], ["--root", str(self.project.resolve()), "--scope", "README.md",
                                        "--scope", "docs"])
        # delegation-continue-parity D174: a project's disableAllHooks cannot switch the hook off (measured 2026-10-09:
        # flag settings override the project's `true`).
        self.assertEqual(json.loads(scoped[index + 1]).keys(), {"hooks", "disableAllHooks"})
        self.assertIs(json.loads(scoped[index + 1])["disableAllHooks"], False)

    def test_a_server_level_allow_rule_covers_that_servers_tools_only(self):
        # delegation-continue-parity D174: Claude Code honours `mcp__<server>`; pre-flight must agree.
        from session_delegation_claude import _matches_rule
        self.assertTrue(_matches_rule("mcp__agent-relay", "mcp__agent-relay__bridge_send"))
        self.assertTrue(_matches_rule("mcp__agent-relay__*", "mcp__agent-relay__bridge_send"))
        self.assertFalse(_matches_rule("mcp__agent-relay", "mcp__agent-relay-other__bridge_send"))
        self.assertFalse(_matches_rule("mcp__agent", "mcp__agent-relay__bridge_send"))
        self.assertFalse(_matches_rule("Read", "mcp__agent-relay__bridge_send"))
        self.write_permissions(["mcp__agent-relay"])
        readiness = inspect_project_permissions(self.project, "safe-review", None, server_name="agent-relay")
        self.assertTrue(readiness.ready, readiness)

    def test_only_the_two_cross_host_intents_have_a_launch_shape(self):
        # delegation-continue-parity D174: the host-native branches are gone with host-native (0.6.0).
        from session_delegation_claude import _permission_shape
        for intent, host_permission in (("host-native", "plan"), ("host-native", "dontAsk"), ("other", None)):
            with self.subTest(intent=intent, host_permission=host_permission):
                with self.assertRaisesRegex(ClaudeAdapterError, "permission-intent-unsupported"):
                    _permission_shape(intent, host_permission, "agent-relay")

    def test_resume_repeats_every_launch_limit_of_create(self):
        # delegation-continue-parity D171: the same limits, built by one function, for every launch shape.
        installation = ClaudeInstallation(Path("/opt/claude"), "2.1.295")
        config = Path("/private/tmp/session.mcp.json")
        for intent in ("safe-review", "bounded-development"):
            for host_permission in (None, "user-environment"):
                for scope in ((), ("README.md",)):
                    if scope and intent != "safe-review":
                        continue
                    with self.subTest(intent=intent, environment=host_permission, scope=scope):
                        create = list(build_create_command(
                            installation, config, "agent-relay-12345678", "Go", intent, "dontAsk", host_permission,
                            scope=scope, scope_root=self.project))
                        resume = list(build_resume_command(
                            installation, config, "session-uuid", "Go", intent, "dontAsk", host_permission,
                            scope=scope, scope_root=self.project))
                        name = create.index("--name")
                        expected = create[:name] + create[name + 2:]
                        expected[2:2] = ["--resume", "session-uuid"]
                        self.assertEqual(resume, expected)
                        for flag in ("--strict-mcp-config", "--permission-mode", "--tools", "--setting-sources",
                                     "--permission-prompts", "--no-chrome"):
                            self.assertIn(flag, resume)
                        self.assertEqual("--settings" in resume, bool(scope))

    def test_host_prompt_allows_control_envelope_after_maximum_user_body(self):
        prompt = _bounded_prompt(
            "x" * 20_800, "12345678-1234-1234-1234-123456789abc",
            "review", COMMUNICATION_TOOLS, "safe-review")
        self.assertIn("<agent-relay-control>", prompt)
        with self.assertRaisesRegex(ClaudeAdapterError, "delegation-prompt-invalid"):
            _bounded_prompt(
                "x" * 24_001, "12345678-1234-1234-1234-123456789abc",
                "review", COMMUNICATION_TOOLS, "safe-review")

    def test_native_backend_uses_its_own_exact_tool_names_and_project_allow_rules(self):
        server_name = "agent-relay"
        rules = communication_rules(server_name)
        self.write_permissions(rules)
        readiness = inspect_project_permissions(
            self.project, "safe-review", None, server_name=server_name,
        )
        self.assertTrue(readiness.ready)
        command = build_create_command(
            ClaudeInstallation(Path("/opt/claude"), "2.1.288"),
            Path("/private/tmp/session.mcp.json"),
            "agent-relay-12345678", "Review", "safe-review", "dontAsk",
            server_name=server_name,
        )
        tools = command[command.index("--tools") + 1]
        self.assertIn("mcp__agent-relay__bridge_register", tools)
        self.assertNotIn("mcp__spec-guard-collaboration__bridge_register", tools)

    def test_native_registration_does_not_bind_general_wake_for_write_permission(self):
        prompt = _bounded_prompt(
            "Implement", "12345678-1234-1234-1234-123456789abc", "dev",
            COMMUNICATION_TOOLS, "bounded-development",
        )
        self.assertIn("call bridge_register exactly once", prompt)
        self.assertIn("wake null", prompt)
        with self.assertRaisesRegex(ClaudeAdapterError, "communication-tools-invalid"):
            communication_rules("unsafe", ("ask_codex",))

    def test_permission_preflight_rules_include_only_prompting_tools(self):
        review = required_project_allow("safe-review", None)
        self.assertEqual(review, CLAUDE_COMMUNICATION_RULES)
        development = required_project_allow("bounded-development", None)
        self.assertEqual(development[-3:], ("Edit", "Write", "Bash"))
        self.assertNotIn("Read", development)

    def test_environment_strips_both_hosts_session_identity(self):
        environment = sanitized_environment({
            "PATH": "/bin", "CODEX_THREAD_ID": "codex",
            "CODEX_SESSION_ID": "codex-session",
            "CLAUDE_CODE_SESSION_ID": "claude",
        })
        self.assertEqual(environment, {"PATH": "/bin", "NO_COLOR": "1"})


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
            "name": "agent-relay-" + self.claim.delegation_id[:8],
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

    def adapter(self, runner, *, wake=None, registration_probe=None, sleep=None):
        return ClaudeAdapter(
            self.store,
            self.installation,
            self.root,
            runner=runner,
            config_factory=lambda _delegation_id: self.config,
            native_wake=wake,
            registration_probe=registration_probe,
            now=lambda: NOW,
            sleep=sleep or (lambda _delay: None),
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

    def test_create_retries_only_the_exact_id_during_transient_metadata_startup(self):
        pending = self.entry(state="working", status="busy")
        pending.pop("state")
        delays = []
        runner = ScriptedRunner([
            completed("backgrounded · ce5b9501 · test\n"),
            completed("[]"),
            completed(json.dumps([pending])),
            completed(json.dumps([self.entry(state="working", status="busy")])),
        ])

        result = self.adapter(runner, sleep=delays.append).create(
            self.claim.delegation_id, "Review")

        self.assertEqual(result.state, "created")
        self.assertEqual(result.host_ref, "ce5b9501")
        self.assertEqual(delays, [0.2, 0.5])
        list_calls = [call for call, _kwargs in runner.calls if "agents" in call]
        self.assertEqual(len(list_calls), 3)

    def test_persistently_incomplete_exact_entry_preserves_host_ref_as_unknown(self):
        pending = self.entry(state="working", status="busy")
        pending.pop("state")
        runner = RepeatingRunner([
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([pending])),
        ])

        result = self.adapter(runner).create(self.claim.delegation_id, "Review")

        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.host_ref, "ce5b9501")
        self.assertEqual(result.prerequisite, "host-entry-invalid")
        stored = self.store.get_delegation(self.claim.delegation_id)
        self.assertEqual(stored.state, "unknown")
        self.assertEqual(stored.host_ref, "ce5b9501")

    def late_entry(self, short_id="ce5b9501"):
        entry = self.entry(short_id=short_id, state="done", status="idle")
        entry["sessionId"] = short_id + "-0817-479d-886e-772bafbbee6f"
        return entry

    def test_create_waits_for_a_background_entry_that_appears_late(self):
        # Claude Code 2.1.291 lists the background session seconds after `--background`
        # returns (round 1 finding 7); 0.7 s of retries made such a create `unknown`.
        delays = []
        runner = ScriptedRunner([
            completed("backgrounded · ce5b9501 · test\n"),
            *[completed("[]") for _ in range(5)],
            completed(json.dumps([self.late_entry()])),
        ])

        result = self.adapter(runner, sleep=delays.append).create(
            self.claim.delegation_id, "Review")

        self.assertEqual(result.state, "created")
        self.assertEqual(result.host_session_ref, self.late_entry()["sessionId"])
        self.assertGreater(sum(delays), 0.7)
        self.assertLessEqual(sum(delays), 10)

    def test_session_started_in_a_git_worktree_is_found_without_the_hosts_cwd_filter(self):
        # Task 4 capture, Claude Code 2.1.291: a background session started in a git worktree
        # reports cwd = the worktree, yet `agents --cwd <worktree>` never lists it.
        def host(command, **_kwargs):
            if "--background" in command:
                return completed("backgrounded · ce5b9501\n")
            if "--cwd" in command:
                return completed("[]")
            return completed(json.dumps([
                self.entry(short_id="0f00ba44", state="done", status="idle") | {
                    "sessionId": "0f00ba44-0817-479d-886e-772bafbbee6f",
                    "cwd": str(self.root.resolve()),
                },
                self.late_entry(),
            ]))
        host.calls = []

        result = self.adapter(host).create(self.claim.delegation_id, "Review")

        self.assertEqual(result.state, "created")
        self.assertEqual(result.host_session_ref, self.late_entry()["sessionId"])

    def test_create_past_the_bound_is_pending_and_the_next_status_binds_it(self):
        delays = []
        creating = RepeatingRunner([
            completed("backgrounded · ce5b9501 · test\n"),
            completed("[]"),
        ])

        created = self.adapter(creating, sleep=delays.append).create(
            self.claim.delegation_id, "Review")

        self.assertEqual(created.state, "unknown")
        self.assertEqual(created.prerequisite, "host-entry-pending")
        self.assertAlmostEqual(sum(delays), 10)
        stored = self.store.get_delegation(self.claim.delegation_id)
        self.assertEqual((stored.host_ref, stored.host_session_ref), ("ce5b9501", None))

        status = self.adapter(ScriptedRunner([
            completed(json.dumps([self.late_entry()])),
        ])).status(self.claim.delegation_id)

        self.assertEqual(status.state, "created")
        stored = self.store.get_delegation(self.claim.delegation_id)
        self.assertEqual(stored.state, "created")
        self.assertEqual(stored.host_session_ref, self.late_entry()["sessionId"])

    def test_continue_binds_a_late_entry_instead_of_refusing_the_follow_up(self):
        self.adapter(RepeatingRunner([
            completed("backgrounded · ce5b9501 · test\n"),
            completed("[]"),
        ])).create(self.claim.delegation_id, "Review")
        woken = []
        entry = json.dumps([self.late_entry()])
        adapter = self.adapter(
            RepeatingRunner([completed(entry)]),
            wake=lambda session_ref, prompt: woken.append(session_ref) or "turn-2",
            registration_probe=lambda *_args: True,
        )

        result = adapter.continue_turn(self.claim.delegation_id, "Again")

        self.assertEqual(result.state, "running")
        self.assertEqual(woken, [self.late_entry()["sessionId"]])

    def test_second_round_to_an_idle_active_target_is_woken_not_reported_busy(self):
        # Baseline finding 4: `continue` answered held/target-busy while hostStatus=idle.
        # The reconcile rule kept (active, idle) running while continue_turn itself treats
        # it as idle enough to wake (D17).
        self.adapter(self.runner_for_create()).create(self.claim.delegation_id, "Review")
        woken = []
        adapter = self.adapter(
            RepeatingRunner([completed(json.dumps([
                self.entry(state="active", status="idle")]))]),
            wake=lambda session_ref, prompt: woken.append(session_ref) or "turn-2",
            registration_probe=lambda *_args: True,
        )

        result = adapter.continue_turn(self.claim.delegation_id, "Again")

        self.assertEqual(result.state, "running")
        self.assertEqual(woken, ["ce5b9501-0817-479d-886e-772bafbbee6f"])

    def test_working_target_is_still_busy_and_an_unrecognised_idle_state_is_named(self):
        self.adapter(self.runner_for_create()).create(self.claim.delegation_id, "Review")
        for state, status, prerequisite in (("working", "busy", "target-busy"),
                                            ("paused", "idle", "target-status-unknown")):
            with self.subTest(state=state):
                adapter = self.adapter(
                    RepeatingRunner([completed(json.dumps([
                        self.entry(state=state, status=status)]))]),
                    wake=lambda *_args: self.fail("must not wake"),
                    registration_probe=lambda *_args: True,
                )

                result = adapter.continue_turn(self.claim.delegation_id, "Again")

                self.assertEqual(result.state, "held")
                self.assertEqual(result.prerequisite, prerequisite)

    def test_round_one_unknown_row_without_session_ref_is_bound_by_status(self):
        # Shape of round 1's row: host_ref 244e528e, no host_session_ref, state unknown.
        _envelope, claim = self.make_claim(key="claude-round1-sample")
        self.store.record_host_unknown(claim.delegation_id, "244e528e")

        result = self.adapter(ScriptedRunner([
            completed(json.dumps([self.late_entry("244e528e")])),
        ])).status(claim.delegation_id)

        self.assertEqual(result.state, "created")
        self.assertEqual(self.store.get_delegation(claim.delegation_id).host_session_ref,
                         self.late_entry("244e528e")["sessionId"])

    def test_late_entry_still_absent_or_invalid_stays_unknown_and_unbound(self):
        foreign = self.late_entry()
        foreign["cwd"] = str(self.root.resolve())
        for listing, prerequisite in (("[]", "host-entry-pending"),
                                      (json.dumps([foreign]), "host-entry-invalid")):
            with self.subTest(prerequisite=prerequisite):
                _envelope, claim = self.make_claim(key="claude-late-" + prerequisite)
                self.store.record_host_unknown(claim.delegation_id, "ce5b9501")

                result = self.adapter(ScriptedRunner([
                    completed(listing),
                ])).status(claim.delegation_id)

                self.assertEqual(result.state, "unknown")
                self.assertEqual(result.prerequisite, prerequisite)
                stored = self.store.get_delegation(claim.delegation_id)
                self.assertEqual(stored.state, "unknown")
                self.assertIsNone(stored.host_session_ref)

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
        # delegation-continue-parity D171: --resume keeps the conversation, not the limits (measured 2026-10-09), so
        # a resumed turn repeats the launch limits; only --name stays create-only.
        self.assertEqual(resume[:-1], list(build_resume_command(
            self.installation, self.config, "ce5b9501-0817-479d-886e-772bafbbee6f", "x", "safe-review", "dontAsk",
            scope=(), scope_root=self.project))[:-1])
        for forbidden in ("--name", "--model", "--settings"):
            self.assertNotIn(forbidden, resume)

    def scoped_claim(self, scope):
        self.store = DelegationStore(self.root / "state", now=lambda: NOW)
        request = AuthorizationRequest(
            authority="direct-user", horizon="task", origin_host="codex", origin_session="origin-session",
            project_root=self.project, repo_identity="git:example/project", baseline="a" * 40, dirty=False,
            target_hosts=("claude",), permission_intent="safe-review", host_permission=None, max_sessions=1,
            expires_at=NOW + 600, depth=0, idempotency_key="claude-scoped-123", summary="Review README")
        envelope = self.store.authorize(request)
        self.claim = self.store.claim_launch(envelope.envelope_id, "claude-scoped-launch", "claude", self.project,
                                             "a" * 40, "safe-review", scope=scope)
        self.complete_claim()

    def test_a_stopped_scoped_review_resumes_with_its_scope_hook(self):
        (self.project / "README.md").write_text("readme", encoding="utf-8")
        self.scoped_claim(("README.md",))
        runner = ScriptedRunner([
            completed(json.dumps([self.entry(state="stopped", status="stopped")])),
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ])
        self.adapter(runner).continue_turn(self.claim.delegation_id, "And the license?")
        resume = runner.calls[1][0]
        self.assertEqual(resume.count("--settings"), 1)
        hook = json.loads(resume[resume.index("--settings") + 1])["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertTrue(hook.endswith("--scope README.md"), hook)

    def test_a_review_recorded_before_schema_three_is_not_continued(self):
        import sqlite3
        self.complete_claim()
        with sqlite3.connect(self.store.database) as connection:
            connection.execute("UPDATE delegations SET scope = NULL")
        runner = ScriptedRunner([])
        with self.assertRaisesRegex(ClaudeAdapterError, "scope-unknown"):
            self.adapter(runner).continue_turn(self.claim.delegation_id, "Again")
        self.assertEqual(runner.calls, [], "no host is touched")

    def test_development_recorded_before_schema_three_still_continues(self):
        import sqlite3
        self.envelope, self.claim = self.make_claim(permission="bounded-development", key="claude-dev-12345")
        result = self.adapter(self.runner_for_create()).create(self.claim.delegation_id, "Go", isolated_worktree=True)
        self.store.set_turn_ref(self.claim.delegation_id, result.host_session_ref)
        for state in ("registered", "running", "completed"):
            self.store.advance(self.claim.delegation_id, state, "host-" + state)
        with sqlite3.connect(self.store.database) as connection:
            connection.execute("UPDATE delegations SET scope = NULL")
        runner = ScriptedRunner([
            completed(json.dumps([self.entry(state="stopped", status="stopped")])),
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ])
        self.adapter(runner).continue_turn(self.claim.delegation_id, "Next step", isolated_worktree=True)
        resume = runner.calls[1][0]
        self.assertIn("--permission-mode", resume)
        self.assertNotIn("--settings", resume)

    def test_stopped_follow_up_retries_transient_post_resume_metadata(self):
        self.complete_claim()
        stopped = self.entry(state="stopped", status="stopped")
        incomplete = self.entry(state="running", status="working")
        incomplete.pop("state")
        delays = []
        runner = ScriptedRunner([
            completed(json.dumps([stopped])),
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([incomplete])),
            completed(json.dumps([incomplete])),
            completed(json.dumps([
                self.entry(state="running", status="working"),
            ])),
        ])

        result = self.adapter(runner, sleep=delays.append).continue_turn(
            self.claim.delegation_id, "Check again")

        self.assertEqual(result.state, "running")
        self.assertEqual(result.host_status, "working")
        self.assertEqual(delays, [0.2, 0.5])
        resume_calls = [
            command for command, _kwargs in runner.calls if "--resume" in command
        ]
        self.assertEqual(len(resume_calls), 1)

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

    def test_cancel_never_launched_claim_is_cancelled_without_host_stop(self):
        for state in ("creating",):
            with self.subTest(state=state):
                _envelope, claim = self.make_claim(key="claude-never-" + state)
                managed = self.store.root / (
                    "claude-" + claim.delegation_id + ".mcp.json")
                managed.write_text('{"mcpServers":{}}\n', encoding="utf-8")
                managed.chmod(0o600)
                runner = ScriptedRunner([])

                result = self.adapter(runner).cancel(claim.delegation_id)

                self.assertEqual(result.state, "cancelled")
                self.assertEqual(runner.calls, [])
                self.assertEqual(self.store.get_delegation(claim.delegation_id).state,
                                 "cancelled")
                self.assertEqual(self.store.get_authorization(claim.envelope_id).state,
                                 "cancelled")
                self.assertFalse(managed.exists())

    def test_cancel_unknown_claim_without_host_ref_is_never_reported_cancelled(self):
        # Live C7: the create answered unknown without a host_ref while its session ran;
        # D16 then said cancelled without stopping it. Without an id nothing is stopped
        # or looked up by name, so the answer stays unknown (D16 narrowed).
        _envelope, claim = self.make_claim(key="claude-unparsed-cancel")
        self.store.record_host_unknown(claim.delegation_id)
        runner = ScriptedRunner([])

        result = self.adapter(runner).cancel(claim.delegation_id)

        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.prerequisite, "host-ref-missing")
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.store.get_delegation(claim.delegation_id).state, "unknown")
        self.assertEqual(self.store.get_authorization(claim.envelope_id).state, "cancelled")

    def test_status_and_continue_of_an_unknown_claim_without_host_ref_name_it(self):
        _envelope, claim = self.make_claim(key="claude-unparsed-status")
        self.store.record_host_unknown(claim.delegation_id)
        runner = ScriptedRunner([])

        status = self.adapter(runner).status(claim.delegation_id)
        follow_up = self.adapter(runner).continue_turn(claim.delegation_id, "Again")

        for result in (status, follow_up):
            self.assertEqual(result.state, "unknown")
            self.assertEqual(result.prerequisite, "host-ref-missing")
        self.assertEqual(runner.calls, [])

    def test_create_without_a_parsable_line_names_it_and_reports_a_redacted_diagnostic(self):
        # Live C7b: create answered unknown with no prerequisite and no trace of what
        # `claude --bg` printed, so the cause could not be read back.
        cases = (
            (completed("Starting background service at /Users/someone/.claude/x\nqueued\n",
                       "warn: /private/tmp/secret/path\n"), "rc=0"),
            (ClaudeCommandUncertain("claude-background", "Starting background service…\n"),
             "timeout"),
        )
        for outcome, marker in cases:
            with self.subTest(marker=marker):
                _envelope, claim = self.make_claim(key="claude-diag-" + marker.replace("=", ""))
                runner = ScriptedRunner([outcome])

                result = self.adapter(runner).create(claim.delegation_id, "Review")

                self.assertEqual(result.state, "unknown")
                self.assertEqual(result.prerequisite, "host-ref-missing")
                self.assertIn("claude 2.1.288", result.diagnostic)
                self.assertIn(marker, result.diagnostic)
                self.assertIn("Starting background service", result.diagnostic)
                self.assertNotIn("/Users", result.diagnostic)
                self.assertNotIn("/private", result.diagnostic)
                self.assertEqual(len(runner.calls), 1)

    def test_create_and_cancel_parse_colored_output_from_a_background_origin(self):
        # Live diagnostic (590b2c5): launched from a background Claude session, `--bg`
        # colors the id, and the plain regex missed it (round 1 finding 7, C7).
        colored = ("backgrounded · \x1b[36mce5b9501\x1b[39m · ar-acc-r1fix-diag-fe81b5ea\n"
                   "\x1b[2m  claude agents             list sessions\x1b[22m\n"
                   "\x1b[2m  claude attach ce5b9501    open in this terminal\x1b[22m\n")
        runner = ScriptedRunner([
            completed(colored),
            completed(json.dumps([self.entry()])),
            completed("\x1b[32mstopped\x1b[39m \x1b[36mce5b9501\x1b[39m\n"),
        ])
        adapter = self.adapter(runner)

        created = adapter.create(self.claim.delegation_id, "Review")
        cancelled = adapter.cancel(self.claim.delegation_id)

        self.assertEqual(created.state, "created")
        self.assertEqual(created.host_ref, "ce5b9501")
        self.assertEqual(cancelled.state, "cancelled")

    def test_host_commands_run_without_color(self):
        environment = sanitized_environment({"PATH": "/bin", "FORCE_COLOR": "1"})
        self.assertEqual(environment["NO_COLOR"], "1")
        self.assertNotIn("FORCE_COLOR", environment)

    def test_create_parses_a_background_line_with_a_status_suffix(self):
        runner = ScriptedRunner([
            completed("backgrounded · ce5b9501 (idle — send a prompt to start)\n"),
            completed(json.dumps([self.entry()])),
        ])

        result = self.adapter(runner).create(self.claim.delegation_id, "Review")

        self.assertEqual(result.state, "created")
        self.assertEqual(result.host_ref, "ce5b9501")

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


    # round2-fixes D49 (round 2 R2-6): a target that answered before its mailbox tools connected.
    def unregistered_created_claim(self):
        self.adapter(self.runner_for_create()).create(self.claim.delegation_id, "Review")
        idle = completed(json.dumps([self.entry(state="working", status="idle")]))
        return idle

    def test_envelope_registers_first_and_waits_for_the_mailbox_tools(self):
        prompt = _bounded_prompt("Review", self.claim.delegation_id, "review",
                                 COMMUNICATION_TOOLS, "safe-review")
        control = prompt[prompt.index("<agent-relay-control>"):]
        self.assertIn("Before anything else", control)
        self.assertIn("not listed yet", control)
        self.assertIn("ToolSearch", control)
        self.assertIn("Do not answer before", control)

    def done_entry(self):
        """claude-delegation-realhost D181: Claude Code 2.1.295's `agents --json --all` entry after `claude stop`,
        verbatim in shape (the coordinator, 2026-10-10): state "done", no status, no pid."""
        return {"id": "ce5b9501", "cwd": str(self.project.resolve()), "kind": "background",
                "startedAt": 1791567882687, "sessionId": "ce5b9501-0817-479d-886e-772bafbbee6f",
                "name": "agent-relay-" + self.claim.delegation_id[:8], "state": "done"}

    def test_a_done_session_without_a_pid_is_resumed_with_its_launch_limits(self):
        self.complete_claim()
        runner = ScriptedRunner([
            completed(json.dumps([self.done_entry()])),
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ])
        result = self.adapter(runner).continue_turn(self.claim.delegation_id, "Check again")
        self.assertEqual(result.state, "running", result)
        resume = runner.calls[1][0]
        self.assertEqual(resume[:4], [str(self.installation.binary), "--background", "--resume",
                                      "ce5b9501-0817-479d-886e-772bafbbee6f"])
        self.assertIn("--permission-mode", resume)

    def test_a_done_unregistered_target_gets_the_registration_resent_by_resume(self):
        self.adapter(self.runner_for_create()).create(self.claim.delegation_id, "Review")
        done = completed(json.dumps([self.done_entry()]))
        runner = ScriptedRunner([
            done,  # status: exact entry
            done,  # continue: exact entry
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ])
        result = self.adapter(runner, registration_probe=lambda *_args: False).continue_turn(
            self.claim.delegation_id, "Again")
        self.assertEqual((result.state, result.prerequisite), ("created", "registration-resent"), result)
        resume = runner.calls[2][0]
        self.assertEqual(resume[:3], [str(self.installation.binary), "--background", "--resume"])
        self.assertIn("call bridge_register", resume[-1])
        self.assertFalse(any(command[1:2] == ["stop"] for command, _ in runner.calls), "already stopped")

    def test_continue_resends_the_envelope_once_to_an_idle_unregistered_target(self):
        idle = self.unregistered_created_claim()
        runner = ScriptedRunner([
            idle,  # status: exact entry
            idle,  # continue: exact entry
            completed("stopped ce5b9501\n"),
            completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ])
        adapter = self.adapter(runner, registration_probe=lambda *_args: False)

        result = adapter.continue_turn(self.claim.delegation_id, "Again")

        self.assertEqual((result.state, result.prerequisite), ("created", "registration-resent"))
        resume = runner.calls[3][0]
        self.assertEqual(resume[:4], [str(self.installation.binary), "--background", "--resume",
                                      "ce5b9501-0817-479d-886e-772bafbbee6f"])
        self.assertIn("call bridge_register", resume[-1])
        self.assertIn("Again", resume[-1])
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state, "created")

        again = ScriptedRunner([idle, idle])
        second = self.adapter(again, registration_probe=lambda *_args: False).continue_turn(
            self.claim.delegation_id, "Again")
        self.assertEqual((second.state, second.prerequisite), ("held", "mailbox-registration-missing"))
        self.assertFalse(any("stop" in command or "--resume" in command for command, _ in again.calls))

    def test_a_resent_envelope_still_completes_once_the_target_registers(self):
        idle = self.unregistered_created_claim()
        self.adapter(ScriptedRunner([
            idle, idle, completed("stopped ce5b9501\n"), completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ]), registration_probe=lambda *_args: False).continue_turn(self.claim.delegation_id, "Again")

        result = self.adapter(ScriptedRunner([completed(json.dumps([self.entry()]))]),
                              registration_probe=lambda *_args: True).status(self.claim.delegation_id)

        self.assertEqual(result.state, "completed")

    def test_a_registered_target_idle_with_state_working_takes_the_follow_up(self):
        # C3 plain repository: round 1 registered and returned; the resumed round answered before its bridge
        # reconnected and stopped as status=idle, state=working, which used to hold every later continue.
        self.complete_claim()
        self.store.begin_follow_up(self.claim.delegation_id, "claude-turn-round-2")
        idle = completed(json.dumps([self.entry(state="working", status="idle")]))
        runner = ScriptedRunner([
            idle, idle, completed("stopped ce5b9501\n"), completed("backgrounded · ce5b9501 · test\n"),
            completed(json.dumps([self.entry(state="running", status="working")])),
        ])

        result = self.adapter(runner, registration_probe=lambda *_args: True).continue_turn(
            self.claim.delegation_id, "Round 3")

        self.assertEqual(result.state, "running")
        self.assertTrue(any("--resume" in command for command, _ in runner.calls))


class NativeWakeDefectTests(AdapterTests):
    """A defect in the injected native wake must not be reported as a host result.

    `native_wake` is a seam, so this handler cannot name an exception type -- but it also
    performs a state transition, not just a report: `begin_follow_up` has already run, so
    simply re-raising would strand the delegation mid-follow-up. The guard therefore
    advances the state first and re-raises afterwards, keeping the record recoverable
    while still surfacing the defect. `advance` validates its evidence string against a
    locked enum, so the exception type cannot be carried in the diagnostic instead.
    """

    def _wake_raising(self, error):
        def wake(_session_ref, _prompt):
            raise error
        return wake

    def test_a_defect_in_the_native_wake_propagates(self):
        self.complete_claim()
        adapter = self.adapter(ScriptedRunner([completed(json.dumps([self.entry()]))]),
                               wake=self._wake_raising(AttributeError("no attribute 'typo'")))
        with self.assertRaises(AttributeError):
            adapter.continue_turn(self.claim.delegation_id, "Check again")

    def test_the_delegation_is_still_advanced_before_the_defect_surfaces(self):
        """Losing the state transition would strand the delegation mid-follow-up."""
        self.complete_claim()
        adapter = self.adapter(ScriptedRunner([completed(json.dumps([self.entry()]))]),
                               wake=self._wake_raising(AttributeError("no attribute 'typo'")))
        with self.assertRaises(AttributeError):
            adapter.continue_turn(self.claim.delegation_id, "Check again")
        self.assertEqual(
            self.store.get_delegation(self.claim.delegation_id).state, "unknown")

    def test_a_host_failure_in_the_native_wake_still_degrades(self):
        self.complete_claim()
        adapter = self.adapter(ScriptedRunner([completed(json.dumps([self.entry()]))]),
                               wake=self._wake_raising(RuntimeError("wake transport down")))
        result = adapter.continue_turn(self.claim.delegation_id, "Check again")
        self.assertEqual(result.state, "unknown")


if __name__ == "__main__":
    unittest.main()
