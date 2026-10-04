"""Pure route-selection and public-state contract tests."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from session_routing import RoutingError, select_route, validate_public_outcome


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
            ("claude", "codex", "not-applicable", "spec-guard-bridge"),
            ("codex", "claude", "not-applicable", "spec-guard-bridge"),
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
            "transport": "spec-guard-bridge",
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

    def test_cross_host_bridge_failure_never_switches_to_native_or_another_backend(self):
        for state in ("invalid", "unavailable"):
            with self.subTest(state=state):
                result = select_route(self.facts(
                    targetHost="codex",
                    nativeCapability="not-applicable",
                    bridgeState=state,
                ))
                self.assertEqual(result["action"], "stop")
                self.assertEqual(result["transport"], "spec-guard-bridge")
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
                self.assertEqual(result["transport"], "spec-guard-bridge")
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
            transport="spec-guard-bridge",
            dispatch="enqueued",
            wake="held",
            receipt="unavailable",
            fallbackFrom="host-native-claude",
            routeReason="native-capability-unavailable",
            nextStep="Wait for the joined target to read the message.",
        )
        self.assertEqual(validate_public_outcome(outcome), outcome)

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
            self.outcome(transport="spec-guard-bridge",
                         fallbackFrom="host-native-claude"),
            self.outcome(transport="host-native-claude",
                         fallbackFrom="host-native-codex",
                         routeReason="wrong-transport"),
            self.outcome(transport="spec-guard-bridge",
                         fallbackFrom="spec-guard-bridge",
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
