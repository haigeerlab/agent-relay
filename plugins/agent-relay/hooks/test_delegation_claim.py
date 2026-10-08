"""delegation-claim: one call at a time may reach a host for a delegation (D122-D126)."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest

from session_delegation import (
    AuthorizationRequest, DelegationError, DelegationStore, OperationBusy, OperationClaim)
from session_delegation_control import SessionDelegationController
from test_session_delegation_recovery import FakeAdapter


NOW = 1_800_000_000
DELEGATION = "11111111-2222-4333-8444-555555555555"


class ClaimFileTests(unittest.TestCase):
    """D122: a private lock file per delegation, held exclusively, carrying the operation in flight."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ar-claim-")
        self.addCleanup(temporary.cleanup)
        self.store = DelegationStore(Path(temporary.name) / "state", now=lambda: NOW)
        self.path = self.store.root / "claims" / (DELEGATION + ".lock")

    def test_the_claim_file_is_private_and_starts_clean(self):
        with OperationClaim(self.store, DELEGATION) as claim:
            self.assertEqual(claim.previous(), "")
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_a_second_holder_is_refused_while_the_first_holds_it(self):
        with OperationClaim(self.store, DELEGATION):
            with self.assertRaises(OperationBusy):
                with OperationClaim(self.store, DELEGATION):
                    self.fail("a second holder must not get the claim")
        with OperationClaim(self.store, DELEGATION):
            pass  # released with the first holder

    def test_another_process_holding_the_lock_makes_it_busy(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(OperationBusy):
                with OperationClaim(self.store, DELEGATION):
                    pass
        finally:
            os.close(descriptor)

    def test_begin_is_durable_and_end_clears_it(self):
        with OperationClaim(self.store, DELEGATION) as claim:
            claim.begin("create")
        with OperationClaim(self.store, DELEGATION) as claim:
            self.assertEqual(claim.previous(), "create", "a holder that died leaves its operation")
            claim.end()
        with OperationClaim(self.store, DELEGATION) as claim:
            self.assertEqual(claim.previous(), "")
        self.assertEqual(self.path.read_bytes(), b"")

    def test_an_unsafe_claim_file_is_refused(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.store.root / "elsewhere"
        target.write_text("", encoding="utf-8")
        self.path.symlink_to(target)
        with self.assertRaisesRegex(DelegationError, "claim-file-unsafe"):
            with OperationClaim(self.store, DELEGATION):
                pass
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaisesRegex(DelegationError, "claim-file-unsafe"):
            with OperationClaim(self.store, DELEGATION):
                pass

    def test_a_malformed_delegation_id_is_refused(self):
        with self.assertRaisesRegex(DelegationError, "claim-file-unsafe"):
            with OperationClaim(self.store, "../escape"):
                pass



def result(state, prerequisite=None):
    return SimpleNamespace(state=state, host_status=None, prerequisite=prerequisite)


class RaisingAdapter(FakeAdapter):
    def create(self, delegation_id, prompt, isolated_worktree=False):
        self.calls.append(("create", delegation_id, prompt, isolated_worktree))
        raise RuntimeError("adapter failed before reaching a host")


class ControllerClaimTests(unittest.TestCase):
    """D123-D125: the controller claims before any adapter call; busy and interrupted calls never reach a host."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ar-claim-controller-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.store = DelegationStore(self.root / "state", now=lambda: NOW)

    def request(self):
        return AuthorizationRequest(
            authority="direct-user", horizon="task", origin_host="claude", origin_session="origin-session",
            project_root=self.project, repo_identity="git:example/project", baseline="a" * 40, dirty=False,
            target_hosts=("codex",), permission_intent="safe-review", host_permission=None, max_sessions=1,
            expires_at=NOW + 600, depth=0, idempotency_key="claim-request-1", summary="Review current diff")

    def controller(self, *states, adapter_class=FakeAdapter):
        adapter = adapter_class(self.store, [result(state, "project-trust" if state == "held" else None)
                                             for state in states])
        return SessionDelegationController(self.store, lambda _host, _project: adapter), adapter

    def create(self, controller):
        return controller.authorize_and_create(
            self.request(), "claim-launch-1", "复审", "Review", target_host="codex", permission_intent="safe-review")

    def prepare_creating(self):
        """A `creating` row whose create has not reached the adapter yet."""
        envelope = self.store.authorize(self.request())
        return self.store.claim_launch(envelope.envelope_id, "claim-launch-1", "codex", self.project, "a" * 40,
                                       "safe-review", friendly_name="复审")

    def prepare_completed(self):
        controller, _adapter = self.controller("created")
        self.create(controller)
        claim = self.store.list_delegations()[0]
        self.store.set_turn_ref(claim.delegation_id, "turn-initial-1")
        for state, evidence in (("registered", "host-registered"), ("running", "host-running"),
                                ("completed", "host-completed")):
            self.store.advance(claim.delegation_id, state, evidence)
        return claim

    def claim_file(self, delegation_id):
        return self.store.root / "claims" / (delegation_id + ".lock")

    def test_a_create_while_another_call_holds_the_claim_does_not_reach_the_host(self):
        claim = self.prepare_creating()
        controller, adapter = self.controller("created")
        with OperationClaim(self.store, claim.delegation_id):
            public = self.create(controller)
        self.assertEqual(adapter.calls, [])
        self.assertEqual(public.prerequisite, "operation-in-progress")
        self.assertEqual(public.host_operation, "create")
        self.assertEqual(self.store.get_delegation(claim.delegation_id).state, "creating")

    def test_a_continue_while_another_call_holds_the_claim_does_not_reach_the_host(self):
        claim = self.prepare_completed()
        controller, adapter = self.controller("completed")
        with OperationClaim(self.store, claim.delegation_id):
            public = controller.continue_named("复审", "Again")
        self.assertEqual(adapter.calls, [])
        self.assertEqual(public.prerequisite, "operation-in-progress")
        self.assertEqual(public.host_operation, "continue")
        self.assertEqual(self.store.get_delegation(claim.delegation_id).state, "completed")

    def test_a_create_left_half_way_is_reported_unknown_and_never_launched_again(self):
        claim = self.prepare_creating()
        with OperationClaim(self.store, claim.delegation_id) as held:
            held.begin("create")  # the holder dies here: the flock goes, the operation stays
        controller, adapter = self.controller("created")
        public = self.create(controller)
        self.assertEqual(adapter.calls, [])
        self.assertEqual((public.state, public.prerequisite), ("unknown", "previous-operation-interrupted"))
        self.assertEqual(self.store.get_delegation(claim.delegation_id).state, "unknown")
        self.assertEqual(self.claim_file(claim.delegation_id).read_bytes(), b"")

    def test_a_continue_left_half_way_is_reported_unknown_and_never_sent_again(self):
        claim = self.prepare_completed()
        with OperationClaim(self.store, claim.delegation_id) as held:
            held.begin("continue")
        controller, adapter = self.controller("completed")
        public = controller.continue_named("复审", "Again")
        self.assertEqual(adapter.calls, [])
        self.assertEqual((public.state, public.prerequisite), ("unknown", "previous-operation-interrupted"))
        self.assertEqual(self.store.get_delegation(claim.delegation_id).state, "unknown")
        self.assertEqual(self.claim_file(claim.delegation_id).read_bytes(), b"")

    def test_a_held_create_releases_the_claim_and_a_retry_proceeds(self):
        controller, adapter = self.controller("held", "created")
        first = self.create(controller)
        self.assertEqual(first.state, "held")
        claim = self.store.list_delegations()[0]
        self.assertEqual(self.claim_file(claim.delegation_id).read_bytes(), b"")
        second = self.create(controller)
        self.assertEqual([call[0] for call in adapter.calls], ["create", "create"])
        self.assertEqual(second.state, "created")

    def test_an_adapter_error_still_empties_the_claim(self):
        controller, adapter = self.controller(adapter_class=RaisingAdapter)
        with self.assertRaises(RuntimeError):
            self.create(controller)
        claim = self.store.list_delegations()[0]
        self.assertEqual(self.claim_file(claim.delegation_id).read_bytes(), b"")
        self.assertEqual(len(adapter.calls), 1)

    def test_two_processes_creating_the_same_launch_reach_the_host_once(self):
        calls = self.root / "calls.log"
        script = textwrap.dedent(f"""
            import sys, time
            from pathlib import Path
            from types import SimpleNamespace
            sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})
            from session_delegation import AuthorizationRequest, DelegationStore
            from session_delegation_control import SessionDelegationController
            store = DelegationStore(Path({str(self.store.root)!r}), now=lambda: {NOW})
            class Slow:
                def create(self, delegation_id, prompt, isolated_worktree=False):
                    with open({str(calls)!r}, "a") as handle:
                        handle.write(delegation_id + "\\n")
                    time.sleep(1.5)
                    store.bind_host(delegation_id, "host-1", "session-1", "test", "readOnly/never")
                    return SimpleNamespace(state="created", host_status=None, prerequisite=None)
            request = AuthorizationRequest(
                authority="direct-user", horizon="task", origin_host="claude", origin_session="origin-session",
                project_root=Path({str(self.project)!r}), repo_identity="git:example/project", baseline="a" * 40,
                dirty=False, target_hosts=("codex",), permission_intent="safe-review", host_permission=None,
                max_sessions=1, expires_at={NOW + 600}, depth=0, idempotency_key="claim-request-1",
                summary="Review current diff")
            controller = SessionDelegationController(store, lambda _h, _p: Slow())
            public = controller.authorize_and_create(request, "claim-launch-1", "复审", "Review",
                                                     target_host="codex", permission_intent="safe-review")
            print(public.state, public.prerequisite)
        """)
        processes = [subprocess.Popen([sys.executable, "-B", "-c", script], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outputs = [process.communicate(timeout=60) for process in processes]
        for process, (_out, err) in zip(processes, outputs):
            self.assertEqual(process.returncode, 0, err)
        self.assertEqual(len(calls.read_text(encoding="utf-8").splitlines()), 1, outputs)
        self.assertIn("operation-in-progress", " ".join(out for out, _err in outputs))


if __name__ == "__main__":
    unittest.main()
