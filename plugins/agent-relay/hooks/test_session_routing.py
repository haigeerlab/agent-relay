"""Pure route-selection and public-state contract tests."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from session_routing import (
    CODEX_WORK_HINT, CODEX_WORK_JOIN_HINT, JOIN_HINT, JOIN_SENTENCE, RoutingError, select_route,
    validate_public_outcome,
)


HOOK = Path(__file__).with_name("session_routing.py")


class RouteSelectionTests(unittest.TestCase):
    def facts(self, **overrides):
        values = {
            "originHost": "claude",
            "targetHost": "claude",
            "authorizationState": "authorized",
            "targetResolution": "unique",
            "nativeCapability": "available",
            "nativeDispatch": "not-attempted",
            "bridgeState": "unavailable",
            "originJoined": False,
            "targetJoined": False,
        }
        values.update(overrides)
        return values

    def test_four_route_matrix_selects_one_primary_transport(self):
        cases = (
            ("claude", "claude", "available", "host-native-claude"),
            ("codex", "codex", "available", "host-native-codex"),
            ("claude", "codex", "not-applicable", "agent-relay-bridge"),
            ("codex", "claude", "not-applicable", "agent-relay-bridge"),
        )
        for origin, target, capability, transport in cases:
            with self.subTest(origin=origin, target=target):
                cross_host = origin != target
                result = select_route(self.facts(
                    originHost=origin,
                    targetHost=target,
                    nativeCapability=capability,
                    bridgeState="ready" if cross_host else "unavailable",
                    originJoined=cross_host,
                    targetJoined=cross_host,
                ))
                self.assertEqual(result["action"], "dispatch")
                self.assertEqual(result["transport"], transport)
                self.assertNotIn("fallbackFrom", result)

    def test_same_host_native_unavailable_has_explicit_bounded_fallback(self):
        result = select_route(self.facts(
            nativeCapability="unavailable",
            bridgeState="ready",
            originJoined=True,
            targetJoined=True,
        ))
        self.assertEqual(result, {
            "schemaVersion": 1,
            "action": "dispatch",
            "transport": "agent-relay-bridge",
            "routeReason": "native-capability-unavailable",
            "fallbackFrom": "host-native-claude",
        })

    def test_fallback_requires_current_authorization_ready_bridge_and_both_joins(self):
        cases = (
            ({"authorizationState": "unauthorized"}, "authorization-required"),
            ({"authorizationState": "unknown"}, "authorization-unknown"),
            ({"bridgeState": "unavailable"}, "native-unavailable-bridge-unavailable"),
            ({"bridgeState": "invalid"}, "native-unavailable-bridge-invalid"),
            ({"originJoined": False}, "native-unavailable-origin-not-joined"),
            ({"targetJoined": False}, "native-unavailable-target-not-joined"),
        )
        base = {
            "nativeCapability": "unavailable",
            "bridgeState": "ready",
            "originJoined": True,
            "targetJoined": True,
        }
        for overrides, reason in cases:
            with self.subTest(reason=reason):
                result = select_route(self.facts(**(base | overrides)))
                self.assertEqual(result["action"], "stop")
                self.assertEqual(result["routeReason"], reason)
                self.assertNotIn("fallbackFrom", result)

    def test_target_must_be_unique_before_any_route_can_dispatch(self):
        for resolution in ("missing", "ambiguous"):
            with self.subTest(resolution=resolution):
                result = select_route(self.facts(targetResolution=resolution))
                self.assertEqual(result["action"], "stop")
                self.assertEqual(result["routeReason"], "target-" + resolution)

    def test_a_target_that_has_not_joined_gets_the_sentence_that_joins_it(self):
        # join-hint-on-missing-target D192: the stop names the next step instead of ending the flow.
        ready = {"bridgeState": "ready", "originJoined": True, "targetJoined": True}
        cross = ready | {"targetHost": "codex", "nativeCapability": "not-applicable"}
        cases = (
            ({"targetResolution": "missing"}, "target-missing"),
            (cross | {"targetResolution": "missing"}, "target-missing"),
            (cross | {"targetJoined": False}, "target-not-joined"),
            (cross | {"originHost": "codex", "targetHost": "claude", "targetJoined": False}, "target-not-joined"),
            (ready | {"nativeCapability": "unavailable", "targetJoined": False},
             "native-unavailable-target-not-joined"),
        )
        for overrides, reason in cases:
            with self.subTest(reason=reason, overrides=overrides):
                result = select_route(self.facts(**overrides))
                self.assertEqual((result["action"], result["routeReason"]), ("stop", reason))
                self.assertEqual(result["nextStep"], JOIN_HINT)
        self.assertEqual(JOIN_SENTENCE, "加入本机联调并允许唤醒，名字叫 <名字>")
        self.assertIn("“" + JOIN_SENTENCE + "”", JOIN_HINT)
        self.assertLessEqual(len(JOIN_HINT), 240)
        self.assertNotIn("\n", JOIN_HINT)
        # The same text is a valid public nextStep.
        validate_public_outcome({
            "transport": "agent-relay-bridge",
            "target": {"host": "codex", "name": "live-saas-fe", "project": "live-saas"},
            "dispatch": "rejected", "wake": "not-applicable", "receipt": "unavailable", "response": "failed",
            "routeReason": "target-missing", "nextStep": JOIN_HINT,
        })

    def test_no_other_result_carries_a_next_step(self):
        ready = {"bridgeState": "ready", "originJoined": True, "targetJoined": True}
        cross = ready | {"targetHost": "codex", "nativeCapability": "not-applicable"}
        cases = (
            {"targetResolution": "ambiguous"},
            {"authorizationState": "unauthorized"},
            {"authorizationState": "unknown", "targetResolution": "missing"},
            cross,
            cross | {"originJoined": False},
            cross | {"bridgeState": "unavailable"},
            cross | {"bridgeState": "invalid", "targetJoined": False},
            ready | {"nativeCapability": "unavailable"},
            ready | {"nativeCapability": "unavailable", "originJoined": False},
            ready | {"nativeCapability": "unavailable", "originJoined": False, "targetJoined": False},
            ready | {"nativeCapability": "unavailable", "bridgeState": "unavailable", "targetJoined": False},
            {"nativeCapability": "unknown"},
            {}, {"nativeDispatch": "accepted"}, {"nativeDispatch": "unknown"}, {"nativeDispatch": "rejected"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertNotIn("nextStep", select_route(self.facts(**overrides)))

    # codex-request-via-mailbox D195: a Codex task giving work to another Codex task uses the mailbox when both are
    # joined with wake, so the answer comes back with replyTo and wakes the source after it ended its turn.
    def codex(self, **overrides):
        return self.facts(**({"originHost": "codex", "targetHost": "codex", "bridgeState": "ready",
                              "originJoined": True, "targetJoined": True, "originWake": True, "targetWake": True}
                             | overrides))

    def test_codex_work_goes_through_the_mailbox_when_both_are_joined_with_wake(self):
        for exchange in ("assign", "unknown", None):
            with self.subTest(exchange=exchange):
                facts = self.codex() if exchange is None else self.codex(exchange=exchange)
                self.assertEqual("exchange" in facts, exchange is not None)
                self.assertEqual(select_route(facts), {
                    "schemaVersion": 1, "action": "dispatch", "transport": "agent-relay-bridge",
                    "routeReason": "codex-work-via-mailbox",
                })
        ask = select_route(self.codex(exchange="ask"))
        self.assertEqual((ask["action"], ask["transport"], ask["routeReason"]),
                         ("dispatch", "host-native-codex", "primary-native"))
        self.assertNotIn("nextStep", ask)

    def test_codex_work_without_both_wake_bindings_stays_native_and_says_why(self):
        for missing in ({"originJoined": False}, {"targetJoined": False}, {"originWake": False},
                        {"targetWake": False}, {"originWake": None}, {"targetWake": None}):
            with self.subTest(missing=missing):
                facts = self.codex(**{k: v for k, v in missing.items() if v is not None})
                for key, value in missing.items():
                    if value is None:
                        del facts[key]  # absent means not bound
                result = select_route(facts)
                self.assertEqual((result["action"], result["transport"], result["routeReason"]),
                                 ("dispatch", "host-native-codex", "primary-native"))
                self.assertEqual(result["nextStep"], CODEX_WORK_JOIN_HINT)
        for bridge in ("unavailable", "invalid"):
            with self.subTest(bridge=bridge):
                result = select_route(self.codex(bridgeState=bridge, exchange="assign"))
                self.assertEqual((result["transport"], result["nextStep"]), ("host-native-codex", CODEX_WORK_HINT))
        self.assertIn("“" + JOIN_SENTENCE + "”", CODEX_WORK_JOIN_HINT)
        for hint in (CODEX_WORK_HINT, CODEX_WORK_JOIN_HINT):
            self.assertLessEqual(len(hint), 240)
            self.assertNotIn("\n", hint)

    def test_a_native_dispatch_already_made_stays_native(self):
        for dispatch, action in (("accepted", "observe"), ("unknown", "reconcile"), ("rejected", "stop")):
            with self.subTest(dispatch=dispatch):
                result = select_route(self.codex(nativeDispatch=dispatch, exchange="assign"))
                self.assertEqual((result["action"], result["transport"]), (action, "host-native-codex"))
                self.assertNotIn("nextStep", result)
        # Native capability not available keeps today's rules (fallback or reconcile), whatever exchange says.
        unknown = select_route(self.codex(nativeCapability="unknown", exchange="assign"))
        self.assertEqual(unknown["action"], "reconcile")
        fallback = select_route(self.codex(nativeCapability="unavailable", exchange="assign"))
        self.assertEqual((fallback["routeReason"], fallback["fallbackFrom"]),
                         ("native-capability-unavailable", "host-native-codex"))

    def test_exchange_and_wake_change_nothing_for_claude_pairs_or_across_hosts(self):
        extra = {"exchange": "assign", "originWake": True, "targetWake": True}
        ready = {"bridgeState": "ready", "originJoined": True, "targetJoined": True}
        for base in ({}, ready, ready | {"targetHost": "codex", "nativeCapability": "not-applicable"},
                     ready | {"originHost": "codex", "nativeCapability": "not-applicable"}):
            with self.subTest(base=base):
                self.assertEqual(select_route(self.facts(**(base | extra))), select_route(self.facts(**base)))

    def test_exchange_and_wake_values_are_checked(self):
        for bad in ({"exchange": "work"}, {"exchange": None}, {"originWake": "yes"}, {"targetWake": 1}):
            with self.subTest(bad=bad):
                with self.assertRaises(RoutingError):
                    select_route(self.codex(**bad))

    def test_the_selector_takes_no_name(self):
        for field in ("name", "targetName", "suggestedName"):
            with self.subTest(field=field):
                with self.assertRaises(RoutingError):
                    select_route(self.facts(**{field: "LIVE-SAAS｜前端基础架构"}))

    def test_cross_host_bridge_failure_never_switches_to_native_or_another_backend(self):
        for state in ("invalid", "unavailable"):
            with self.subTest(state=state):
                result = select_route(self.facts(
                    targetHost="codex",
                    nativeCapability="not-applicable",
                    bridgeState=state,
                ))
                self.assertEqual(result["action"], "stop")
                self.assertEqual(result["transport"], "agent-relay-bridge")
                self.assertEqual(result["routeReason"], "bridge-" + state)

    def test_cross_host_bridge_requires_both_exact_joined_endpoints(self):
        cases = (
            ({"originJoined": False}, "origin-not-joined"),
            ({"targetJoined": False}, "target-not-joined"),
        )
        base = {
            "targetHost": "codex",
            "nativeCapability": "not-applicable",
            "bridgeState": "ready",
            "originJoined": True,
            "targetJoined": True,
        }
        for overrides, reason in cases:
            with self.subTest(reason=reason):
                result = select_route(self.facts(**(base | overrides)))
                self.assertEqual(result["action"], "stop")
                self.assertEqual(result["transport"], "agent-relay-bridge")
                self.assertEqual(result["routeReason"], reason)

    def test_unknown_native_dispatch_requires_reconciliation_and_never_falls_back(self):
        result = select_route(self.facts(
            nativeDispatch="unknown",
            bridgeState="ready",
            originJoined=True,
            targetJoined=True,
        ))
        self.assertEqual(result["action"], "reconcile")
        self.assertEqual(result["transport"], "host-native-claude")
        self.assertEqual(result["routeReason"], "native-dispatch-unknown")
        self.assertNotIn("fallbackFrom", result)

    def test_known_native_result_is_observed_or_stopped_without_second_dispatch(self):
        accepted = select_route(self.facts(nativeDispatch="accepted"))
        rejected = select_route(self.facts(nativeDispatch="rejected"))
        self.assertEqual(accepted["action"], "observe")
        self.assertEqual(accepted["routeReason"], "native-dispatch-accepted")
        self.assertEqual(rejected["action"], "stop")
        self.assertEqual(rejected["routeReason"], "native-dispatch-rejected")

    def test_route_input_is_exact_and_never_accepts_a_message_body(self):
        with self.assertRaisesRegex(RoutingError, "unexpected-fields: body"):
            select_route(self.facts(body="do not persist me"))
        with self.assertRaisesRegex(RoutingError, "missing-fields: bridgeState"):
            values = self.facts()
            del values["bridgeState"]
            select_route(values)

    def test_inconsistent_native_facts_fail_closed(self):
        cases = (
            {"nativeCapability": "unavailable", "nativeDispatch": "accepted"},
            {"targetHost": "codex", "nativeCapability": "available"},
            {"targetHost": "codex", "nativeCapability": "not-applicable",
             "nativeDispatch": "accepted"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(RoutingError):
                    select_route(self.facts(**overrides))


class PublicOutcomeTests(unittest.TestCase):
    def outcome(self, **overrides):
        values = {
            "transport": "host-native-claude",
            "target": {
                "host": "claude",
                "name": "reviewer",
                "project": "project-a",
            },
            "dispatch": "accepted",
            "wake": "admitted",
            "receipt": "delivered",
            "response": "pending",
        }
        values.update(overrides)
        return values

    def test_public_state_enums_and_optional_fallback_metadata_are_preserved(self):
        outcome = self.outcome(
            transport="agent-relay-bridge",
            dispatch="enqueued",
            wake="held",
            receipt="unavailable",
            fallbackFrom="host-native-claude",
            routeReason="native-capability-unavailable",
            nextStep="Wait for the joined target to read the message.",
        )
        self.assertEqual(validate_public_outcome(outcome), outcome)

    def test_the_pre_split_label_is_refused(self):
        # D10: a stale emitter of the Spec Guard label must fail validation, not pass silently.
        outcome = self.outcome(transport="spec-guard-bridge", dispatch="enqueued", wake="held",
                               receipt="unavailable", fallbackFrom="host-native-claude",
                               routeReason="native-capability-unavailable")
        with self.assertRaises(RoutingError):
            validate_public_outcome(outcome)

    def test_illegal_transport_state_and_extra_fields_fail_closed(self):
        cases = (
            (self.outcome(transport="native"), "transport"),
            (self.outcome(dispatch="sent"), "dispatch"),
            (self.outcome(wake="awake"), "wake"),
            (self.outcome(receipt="seen"), "receipt"),
            (self.outcome(response="done"), "response"),
            (self.outcome(body="secret"), "unexpected-fields: body"),
        )
        for outcome, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(RoutingError, reason):
                    validate_public_outcome(outcome)

    def test_stronger_claims_cannot_be_derived_from_unknown_or_rejected_dispatch(self):
        cases = (
            self.outcome(dispatch="unknown", wake="admitted",
                         receipt="unknown", response="unknown"),
            self.outcome(dispatch="unknown", wake="unknown",
                         receipt="read", response="unknown"),
            self.outcome(dispatch="unknown", wake="unknown",
                         receipt="unknown", response="received"),
            self.outcome(dispatch="rejected", wake="unknown",
                         receipt="acknowledged", response="failed"),
        )
        for outcome in cases:
            with self.subTest(outcome=outcome):
                with self.assertRaisesRegex(RoutingError, "state-evidence"):
                    validate_public_outcome(outcome)

    def test_fallback_metadata_is_complete_and_only_names_native_primary(self):
        cases = (
            self.outcome(transport="agent-relay-bridge",
                         fallbackFrom="host-native-claude"),
            self.outcome(transport="host-native-claude",
                         fallbackFrom="host-native-codex",
                         routeReason="wrong-transport"),
            self.outcome(transport="agent-relay-bridge",
                         fallbackFrom="agent-relay-bridge",
                         routeReason="recursive"),
        )
        for outcome in cases:
            with self.subTest(outcome=outcome):
                with self.assertRaises(RoutingError):
                    validate_public_outcome(outcome)

    def test_target_is_minimal_and_rejects_paths_control_characters_or_ids(self):
        cases = (
            {"host": "claude", "name": "reviewer", "project": "a/b"},
            {"host": "codex", "name": "bad\nname", "project": "project"},
            {"host": "codex", "name": "reviewer", "project": "project",
             "threadId": "hidden"},
        )
        for target in cases:
            with self.subTest(target=target):
                with self.assertRaisesRegex(RoutingError, "target"):
                    validate_public_outcome(self.outcome(target=target))


class CommandLineTests(unittest.TestCase):
    def run_cli(self, command, payload):
        return subprocess.run(
            [sys.executable, "-B", str(HOOK), command],
            input=json.dumps(payload), text=True, capture_output=True, check=False,
        )

    def test_cli_prints_the_join_hint_as_ascii_json(self):
        # The hint is Chinese; the CLI keeps json.dumps' ASCII escapes so a C-locale stdout (Codex's sandbox) cannot
        # fail to encode it. A reader gets the text back with json.loads.
        result = self.run_cli("select", RouteSelectionTests().facts(targetResolution="missing"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.isascii(), result.stdout)
        self.assertEqual(json.loads(result.stdout)["nextStep"], JOIN_HINT)

    def test_cli_uses_json_stdio_and_returns_machine_readable_errors(self):
        valid = RouteSelectionTests().facts()
        success = self.run_cli("select", valid)
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(json.loads(success.stdout)["transport"], "host-native-claude")

        invalid = self.run_cli("select", valid | {"body": "not allowed"})
        self.assertEqual(invalid.returncode, 1)
        self.assertEqual(json.loads(invalid.stdout)["state"], "error")
        self.assertIn("unexpected-fields", json.loads(invalid.stdout)["reason"])
        self.assertNotIn("not allowed", invalid.stdout)


if __name__ == "__main__":
    unittest.main()
