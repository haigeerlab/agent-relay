"""Controller recovery, expiry, ambiguity, and exact-target tests."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from session_delegation import AuthorizationRequest, DelegationStore
from session_delegation_control import (
    ControlError,
    SessionDelegationController,
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

    def request(self, key="controller-request-1", horizon="task", max_sessions=1):
        return AuthorizationRequest(
            authority="direct-user", horizon=horizon, origin_host="claude",
            origin_session="origin-session", project_root=self.project,
            repo_identity="git:example/project", baseline="a" * 40, dirty=False,
            target_hosts=("codex",), permission_intent="safe-review",
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
        serialized = repr(result.payload())
        self.assertNotIn(str(self.project), serialized)
        self.assertNotIn("host-", serialized)
        self.assertNotIn("session-", serialized)

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
        self.assertEqual(len(adapter.calls), 1)

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
        first, _ = self.controller(["created", "created"])
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


if __name__ == "__main__":
    unittest.main()
