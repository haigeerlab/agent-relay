"""Controller recovery, expiry, ambiguity, and exact-target tests."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from session_delegation import AuthorizationRequest, DelegationError, DelegationStore
from session_delegation_control import (
    ControlError,
    SessionDelegationController,
    default_state_root,
    main,
)


NOW = 1_800_000_000


class FakeAdapter:
    def __init__(self, store, results):
        self.store = store
        self.results = results
        self.calls = []

    def create(self, delegation_id, prompt, isolated_worktree=False):
        self.calls.append(("create", delegation_id, prompt, isolated_worktree))
        result = self.results.pop(0)
        if result.state == "created":
            self.store.bind_host(
                delegation_id, "host-" + delegation_id[:8],
                "session-" + delegation_id[:8], "test", "readOnly/never",
            )
        elif result.state == "unknown":
            self.store.record_host_unknown(delegation_id)
        return result

    def continue_turn(self, delegation_id, prompt, isolated_worktree=False):
        self.calls.append(("continue", delegation_id, prompt, isolated_worktree))
        return self.results.pop(0)

    def status(self, delegation_id):
        self.calls.append(("status", delegation_id))
        return self.results.pop(0)

    def cancel(self, delegation_id):
        self.calls.append(("cancel", delegation_id))
        claim = self.store.get_delegation(delegation_id)
        self.store.cancel_authorization(claim.envelope_id)
        self.store.advance(delegation_id, "cancelled", "host-cancelled")
        return self.results.pop(0)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sg-controller-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.clock = [NOW]
        self.store = DelegationStore(self.root / "state", now=lambda: self.clock[0])
        self.adapters = []

    def request(self, key="controller-request-1", horizon="task", max_sessions=1,
                target_host="codex"):
        return AuthorizationRequest(
            authority="direct-user", horizon=horizon, origin_host="claude",
            origin_session="origin-session", project_root=self.project,
            repo_identity="git:example/project", baseline="a" * 40, dirty=False,
            target_hosts=(target_host,), permission_intent="safe-review",
            host_permission=None, max_sessions=max_sessions,
            expires_at=NOW + 600, depth=0, idempotency_key=key,
            summary="Review current diff",
        )

    def controller(self, result_states):
        queue = [SimpleNamespace(state=state, host_status=None, prerequisite=(
            "project-trust" if state == "held" else None)) for state in result_states]
        adapter = FakeAdapter(self.store, queue)
        self.adapters.append(adapter)
        return SessionDelegationController(
            self.store, lambda _host, _project: adapter), adapter

    def create(self, controller, request=None, launch="controller-launch-1", name="复审"):
        return controller.authorize_and_create(
            request or self.request(), launch, name, "Review", target_host="codex",
            permission_intent="safe-review",
        )

    def test_direct_task_launch_is_nonblocking_and_public_result_has_no_internal_identity(self):
        controller, adapter = self.controller(["created"])
        result = self.create(controller)
        self.assertEqual(result.state, "created")
        self.assertEqual(result.host, "Codex")
        self.assertEqual(result.friendly_name, "复审")
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(result.payload()["hostOperation"], "create")
        serialized = repr(result.payload())
        self.assertNotIn(str(self.project), serialized)
        self.assertNotIn("host-", serialized)
        self.assertNotIn("session-", serialized)

    def test_exact_origin_route_is_appended_and_completed_result_is_returned(self):
        route = SimpleNamespace(
            backend="native", recipient="origin-agent",
            key="agent-relay-result:route-1234",
        )
        queue = [SimpleNamespace(
            state="completed", host_status="idle", prerequisite=None,
            final_text=("已审查 /Users/private/project 和 "
                        "/private/tmp/internal.log; 无阻断问题\x7f"),
        )]
        adapter = FakeAdapter(self.store, queue)
        controller = SessionDelegationController(
            self.store,
            lambda _host, _project: adapter,
            result_route_resolver=lambda _envelope, _claim: route,
            result_probe=lambda observed, sender: (
                observed.backend == route.backend
                and observed.recipient == route.recipient
                and observed.key.startswith(route.key + ":")
                and sender.startswith("复审-")
            ),
        )

        result = self.create(controller)

        self.assertEqual(result.state, "completed")
        self.assertEqual(result.result_delivery, "enqueued")
        self.assertEqual(result.host_operation, "create")
        self.assertEqual(result.transport, "agent-relay-bridge")
        self.assertEqual(result.dispatch, "enqueued")
        self.assertEqual(result.wake, "unknown")
        self.assertEqual(result.receipt, "unknown")
        self.assertEqual(result.response, "unknown")
        self.assertEqual(result.route_reason, "cross-host-result-route")
        self.assertEqual(
            result.result,
            "已审查 [private-path] 和 [private-path]; 无阻断问题",
        )
        delivered_prompt = adapter.calls[0][2]
        self.assertIn("bridge_send", delivered_prompt)
        self.assertIn("origin-agent", delivered_prompt)
        self.assertIn(route.key, delivered_prompt)
        self.assertNotIn(route.key, repr(result.payload()))

    def test_a_same_host_request_is_refused_before_any_host_starts(self):
        # delegation-cross-host D158: only Claude Code -> Codex and Codex -> Claude Code.
        controller = SessionDelegationController(
            self.store, lambda _host, _project: self.fail("same-host must not reach a host"))
        with self.assertRaisesRegex((ControlError, DelegationError), "same-host-unsupported"):
            controller.authorize_and_create(
                self.request(key="same-host-request", target_host="claude"),
                "same-host-launch", "同宿主", "Review",
                target_host="claude", permission_intent="safe-review",
            )
        self.assertEqual(tuple(self.store.list_delegations()), ())

    def test_public_results_show_the_user_environment_only_when_chosen(self):
        # delegation-user-context D162.
        from dataclasses import replace
        controller, _adapter = self.controller(["created", "created"])
        base = replace(self.request(key="user-env-request", target_host="claude"), origin_host="codex")
        chosen = controller.authorize_and_create(
            replace(base, host_permission="user-environment"), "user-env-launch", "用户环境", "Review",
            target_host="claude", permission_intent="safe-review").payload()
        self.assertEqual(chosen["environment"], "user")
        plain = controller.authorize_and_create(
            replace(base, idempotency_key="plain-request"), "plain-launch", "默认沙箱", "Review",
            target_host="claude", permission_intent="safe-review").payload()
        self.assertNotIn("environment", plain)

    def test_native_delivery_states_and_retry_keys_are_stable(self):
        for observed, state, expected in (
            (False, "created", "pending"),
            (False, "completed", "missing"),
            (None, "completed", "unverified"),
        ):
            with self.subTest(observed=observed, state=state):
                route = SimpleNamespace(
                    backend="native", recipient="origin-agent",
                    key="agent-relay-result:delivery-1234",
                )
                controller = SessionDelegationController(
                    self.store,
                    lambda _host, _project: self.fail("host not required"),
                    result_route_resolver=lambda _envelope, _claim: route,
                    result_probe=lambda _route, _sender, value=observed: value,
                )
                claim = SimpleNamespace(
                    state=state, target_host="claude", friendly_name="delivery",
                    delegation_id="12345678-1234-1234-1234-123456789abc",
                    host_ref=None,
                )
                self.assertEqual(controller._delivery(route, claim), expected)
                prompt = controller._with_result_route("Review", route, "initial")
                self.assertIn("bridge_send", prompt)
        route = SimpleNamespace(
            backend="native", recipient="origin-agent",
            key="agent-relay-result:delivery-1234",
        )
        first = SessionDelegationController._turn_route(route, "Review", "turn-1")
        retried = SessionDelegationController._turn_route(route, "Review", "turn-1")
        second = SessionDelegationController._turn_route(route, "Review", "turn-2")
        self.assertEqual(first, retried)
        self.assertNotEqual(first.key, second.key)

    def test_invalid_result_route_fails_before_starting_a_host(self):
        adapter = FakeAdapter(self.store, [SimpleNamespace(
            state="created", host_status=None, prerequisite=None,
        )])
        controller = SessionDelegationController(
            self.store,
            lambda _host, _project: adapter,
            result_route_resolver=lambda _envelope, _claim: SimpleNamespace(
                backend="native", recipient="bad\nrecipient", key="bad-key"),
            result_probe=lambda _route, _sender: True,
        )

        with self.assertRaisesRegex(ControlError, "result-route-invalid"):
            self.create(controller)
        self.assertEqual(adapter.calls, [])

    def test_default_state_root_is_the_delegation_directory_under_agent_relay(self):
        # D9: runtime/, delegation/ and backups/ are siblings under ~/.agent-relay.
        with mock.patch("session_delegation_control.Path.home", return_value=Path("/home/u")), \
                mock.patch.dict(os.environ):
            os.environ.pop("AGENT_RELAY_HOME", None)
            self.assertEqual(default_state_root(), Path("/home/u/.agent-relay/delegation"))

    def test_a_pre_split_result_key_is_refused(self):
        # D12: only the agent-relay prefix is accepted; in-flight Spec Guard delegations block migration instead.
        adapter = FakeAdapter(self.store, [SimpleNamespace(
            state="created", host_status=None, prerequisite=None,
        )])
        controller = SessionDelegationController(
            self.store,
            lambda _host, _project: adapter,
            result_route_resolver=lambda _envelope, _claim: SimpleNamespace(
                backend="native", recipient="origin-agent", key="spec-guard-result:route-1234"),
            result_probe=lambda _route, _sender: True,
        )

        with self.assertRaisesRegex(ControlError, "result-route-invalid"):
            self.create(controller)
        self.assertEqual(adapter.calls, [])

    def test_missing_origin_route_is_truthfully_reported_without_guessing(self):
        queue = [SimpleNamespace(
            state="completed", host_status="idle", prerequisite=None,
            final_text="No findings",
        )]
        adapter = FakeAdapter(self.store, queue)
        controller = SessionDelegationController(
            self.store,
            lambda _host, _project: adapter,
            result_route_resolver=lambda _envelope, _claim: None,
            result_probe=lambda _route, _sender: self.fail("must not probe"),
        )

        result = self.create(controller)

        self.assertEqual(result.result_delivery, "recipient-unavailable")
        self.assertEqual(result.result, "No findings")
        self.assertNotIn("bridge_send", adapter.calls[0][2])

    def test_restart_reuses_created_claim_and_never_calls_create_again(self):
        first, adapter = self.controller(["created"])
        self.create(first)
        restarted = SessionDelegationController(
            self.store, lambda _host, _project: self.fail("adapter must not be opened"))
        result = self.create(restarted)
        self.assertEqual(result.state, "created")
        self.assertEqual(len(adapter.calls), 1)

    def test_unknown_creation_is_not_retried_automatically(self):
        first, adapter = self.controller(["unknown"])
        self.create(first)
        restarted = SessionDelegationController(
            self.store, lambda _host, _project: self.fail("unknown must not relaunch"))
        result = self.create(restarted)
        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.host_operation, "create")
        self.assertEqual(len(adapter.calls), 1)

    def test_status_and_cancel_report_lifecycle_without_replaying_message_route(self):
        controller, adapter = self.controller(["created", "created", "cancelled"])
        self.create(controller, name="生命周期")
        status = controller.status_named("生命周期")
        cancelled = controller.cancel_named("生命周期")
        self.assertEqual(status.host_operation, "status")
        self.assertIsNone(status.transport)
        self.assertEqual(cancelled.host_operation, "cancel")
        self.assertIsNone(cancelled.transport)
        self.assertEqual([call[0] for call in adapter.calls], [
            "create", "status", "cancel",
        ])

    def test_an_old_same_host_record_is_listed_and_cancelled_but_never_continued(self):
        # delegation-cross-host D158: a record an older version created between two sessions of one host.
        controller, adapter = self.controller(["created", "cancelled"])
        controller.authorize_and_create(
            self.request(key="old-same-host", horizon="session"),
            "old-launch", "旧会话", "First",
            target_host="codex", permission_intent="safe-review",
        )
        claim = self.store.list_delegations()[0]
        with sqlite3.connect(self.store.database) as connection:
            connection.execute("UPDATE authorizations SET origin_host = 'codex' WHERE envelope_id = ?",
                               (claim.envelope_id,))
        self.assertEqual([c.friendly_name for c in self.store.list_delegations()], ["旧会话"])
        with self.assertRaisesRegex(ControlError, "same-host-unsupported"):
            controller.continue_named("旧会话", "Second")
        self.assertEqual([call[0] for call in adapter.calls], ["create"])
        cancelled = controller.cancel_named("旧会话")
        self.assertEqual(cancelled.state, "cancelled")

    def test_held_prerequisite_can_retry_the_same_claim_without_consuming_capacity(self):
        controller, adapter = self.controller(["held", "created"])
        held = self.create(controller)
        self.assertEqual(held.state, "held")
        self.assertEqual(held.prerequisite, "project-trust")
        retried = self.create(controller)
        self.assertEqual(retried.state, "created")
        self.assertEqual(self.store.count_delegations(
            self.store.list_delegations()[0].envelope_id), 1)
        self.assertEqual(len(adapter.calls), 2)

    def test_new_create_after_held_one_resolves_the_launched_session_by_name(self):
        controller, adapter = self.controller(["held", "created", "created", "completed"])
        held = self.create(controller)
        self.assertEqual(held.state, "held")
        launched = self.create(
            controller,
            request=self.request("controller-request-2"),
            launch="controller-launch-2",
        )
        self.assertEqual(launched.state, "created")

        status = controller.status_named("复审")

        self.assertEqual(status.state, "created")
        [bound] = [claim for claim in self.store.list_delegations()
                   if claim.host_ref is not None]
        self.assertEqual(adapter.calls[-1][1], bound.delegation_id)
        self.assertEqual(len(controller.list()), 2)

        self.store.advance(bound.delegation_id, "registered", "host-registered")
        self.store.set_turn_ref(bound.delegation_id, "turn-1")
        self.store.advance(bound.delegation_id, "running", "host-running")
        self.store.advance(bound.delegation_id, "completed", "host-completed")
        controller.continue_named("复审", "Again")
        self.assertEqual(adapter.calls[-1][:2], ("continue", bound.delegation_id))

    def test_unknown_launch_without_host_ref_counts_as_launched_for_name_lookup(self):
        # Live C7: held 418202 then unknown 501157 (no host_ref) under one name.
        controller, adapter = self.controller(["held", "unknown", "unknown"])
        self.create(controller)
        self.create(
            controller,
            request=self.request("controller-request-2"),
            launch="controller-launch-2",
        )

        controller.status_named("复审")

        [attempted] = [claim for claim in self.store.list_delegations()
                       if claim.state == "unknown"]
        self.assertEqual(adapter.calls[-1][:2], ("status", attempted.delegation_id))

    def test_create_diagnostic_reaches_the_public_answer(self):
        queue = [SimpleNamespace(state="unknown", host_status="unknown",
                                 prerequisite="host-ref-missing",
                                 diagnostic="claude 2.1.291; rc=0; stdout: queued")]
        adapter = FakeAdapter(self.store, queue)
        controller = SessionDelegationController(self.store, lambda _h, _p: adapter)

        payload = self.create(controller).payload()

        self.assertEqual(payload["prerequisite"], "host-ref-missing")
        self.assertEqual(payload["diagnostic"], "claude 2.1.291; rc=0; stdout: queued")

    def test_lone_never_launched_session_still_resolves_by_name(self):
        controller, adapter = self.controller(["held", "held"])
        self.create(controller)

        status = controller.status_named("复审")

        self.assertEqual(status.state, "held")
        self.assertEqual(adapter.calls[-1][1], self.store.list_delegations()[0].delegation_id)

    def test_expired_authorization_blocks_follow_up_before_host_adapter(self):
        controller, _adapter = self.controller(["created"])
        self.create(controller)
        claim = self.store.list_delegations()[0]
        self.store.set_turn_ref(claim.delegation_id, "turn-1")
        self.store.advance(claim.delegation_id, "registered", "host-registered")
        self.store.advance(claim.delegation_id, "running", "host-running")
        self.store.advance(claim.delegation_id, "completed", "host-completed")
        self.clock[0] = NOW + 601
        blocked = SessionDelegationController(
            self.store, lambda _host, _project: self.fail("expired must not reach host"))
        with self.assertRaisesRegex(ControlError, "authorization-expired"):
            blocked.continue_named("复审", "Again")

    def test_same_name_lists_short_disambiguators_and_never_guesses(self):
        first, adapter = self.controller(["created", "created", "cancelled"])
        self.create(first)
        self.create(
            first,
            request=self.request("controller-request-2"),
            launch="controller-launch-2",
        )
        listing = first.list()
        self.assertEqual(len(listing), 2)
        self.assertTrue(all(item.disambiguator and len(item.disambiguator) == 6
                            for item in listing))
        with self.assertRaisesRegex(ControlError, "session-name-ambiguous") as caught:
            first.status_named("复审")
        self.assertEqual(len(caught.exception.candidates), 2)
        self.assertNotIn(str(self.project), repr(caught.exception.candidates))

        selected = first.cancel_named(
            "复审", disambiguator=listing[1].disambiguator)
        self.assertEqual(selected.state, "cancelled")
        self.assertEqual(adapter.calls[-1][1], self.store.list_delegations()[1].delegation_id)

        with self.assertRaisesRegex(ControlError, "session-disambiguator-invalid"):
            first.status_named("复审", disambiguator="not-id")
        with self.assertRaisesRegex(ControlError, "session-disambiguator-not-found"):
            first.status_named("复审", disambiguator="ffffff")

    def test_cancel_targets_the_unique_bound_claim(self):
        controller, adapter = self.controller(["created", "cancelled"])
        self.create(controller, name="要取消")
        result = controller.cancel_named("要取消")
        self.assertEqual(result.state, "cancelled")
        self.assertEqual([call[0] for call in adapter.calls], ["create", "cancel"])

    def test_absent_list_is_empty_and_does_not_initialize_runtime(self):
        state_root = self.root / "absent-state"
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--state-root", str(state_root), "list"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), [])
        self.assertFalse(state_root.exists())

    def test_existing_list_does_not_require_a_host_backend(self):
        controller, _adapter = self.controller(["created"])
        self.create(controller)
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--state-root", str(self.root / "state"), "list"])
        self.assertEqual(result, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload[0]["name"], "复审")
        self.assertNotIn(str(self.project), output.getvalue())
        self.assertNotIn("host-", output.getvalue())
        self.assertNotIn("session-", output.getvalue())

    def test_missing_origin_identity_fails_before_state_initialization(self):
        state_root = self.root / "no-origin-state"
        output = io.StringIO()
        argv = [
            "--state-root", str(state_root), "create",
            "--origin-host", "codex", "--target-host", "claude",
            "--project", str(self.project), "--repo-identity", "git:example/project",
            "--baseline", "a" * 40, "--expires-at", str(NOW),
            "--idempotency-key", "controller-request-no-origin",
            "--launch-key", "controller-launch-no-origin", "--name", "复审",
            "--summary", "Review current diff",
        ]
        with mock.patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
            result = main(argv)
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(output.getvalue())["reason"],
                         "origin-session-unavailable")
        self.assertFalse(state_root.exists())

    def test_permission_preflight_is_read_only_and_never_initializes_control_state(self):
        state_root = self.root / "permission-state"
        output = io.StringIO()
        expected = {
            "backend": "native", "ready": False,
            "requiredAllow": ["mcp__native__bridge_register"],
            "writesPerformed": False,
        }
        with mock.patch(
            "session_delegation_control._permission_preflight",
            return_value=expected,
        ), redirect_stdout(output):
            result = main([
                "--state-root", str(state_root), "permissions",
                "--project", str(self.project),
            ])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), expected)
        self.assertFalse(state_root.exists())


    def test_permission_preflight_names_the_files_it_read_and_explains_a_global_allow(self):
        # delegation-user-context D164.
        from argparse import Namespace
        from session_delegation_claude import COMMUNICATION_TOOLS, communication_rules
        from session_delegation_control import _permission_preflight
        config = self.root / "claude-config"
        config.mkdir()
        (config / "settings.json").write_text(json.dumps({"permissions": {"allow": [
            *communication_rules("agent-relay"), "Skill"]}}), encoding="utf-8")
        backend = SimpleNamespace(name="native", claude_server_name="agent-relay", claude_tools=COMMUNICATION_TOOLS)
        with mock.patch("session_delegation_control._selected_backend", return_value=backend), \
                mock.patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": str(config)}):
            default = _permission_preflight(Namespace(project=self.project, permission="safe-review",
                                                      host_permission=None))
            user = _permission_preflight(Namespace(project=self.project, permission="safe-review",
                                                   host_permission="user-environment"))
        self.assertFalse(default["ready"])
        self.assertEqual(default["settings"], [".claude/settings.local.json", ".claude/settings.json"])
        self.assertIn("does not apply to a default delegated session", default["note"])
        self.assertTrue(user["ready"], user)
        self.assertEqual(user["settings"][-1], str(config / "settings.json"))
        self.assertNotIn("note", user)
        self.assertIn("Skill", user["requiredAllow"])
        self.assertFalse(default["writesPerformed"] or user["writesPerformed"])

if __name__ == "__main__":
    unittest.main()
