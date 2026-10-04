#!/usr/bin/env python3
"""Pure same-Mac session routing policy and public outcome validation.

This module performs no host calls, runtime initialization, or persistence.  It
also rejects message bodies so routing metadata cannot become a transcript.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
HOSTS = frozenset(("claude", "codex"))
TRANSPORTS = frozenset(
    ("host-native-claude", "host-native-codex", "spec-guard-bridge")
)
AUTHORIZATION_STATES = frozenset(("authorized", "unauthorized", "unknown"))
TARGET_RESOLUTIONS = frozenset(("unique", "missing", "ambiguous"))
NATIVE_CAPABILITIES = frozenset(
    ("available", "unavailable", "unknown", "not-applicable")
)
NATIVE_DISPATCHES = frozenset(
    ("not-attempted", "accepted", "rejected", "unknown")
)
BRIDGE_STATES = frozenset(("ready", "unavailable", "invalid"))

DISPATCH_STATES = frozenset(("accepted", "enqueued", "held", "rejected", "unknown"))
WAKE_STATES = frozenset(("admitted", "held", "unavailable", "not-applicable", "unknown"))
RECEIPT_STATES = frozenset(("delivered", "read", "acknowledged", "unavailable", "unknown"))
RESPONSE_STATES = frozenset(("pending", "received", "cancelled", "failed", "unknown"))

_ROUTE_FIELDS = frozenset((
    "originHost", "targetHost", "authorizationState", "targetResolution",
    "nativeCapability", "nativeDispatch", "bridgeState", "originJoined",
    "targetJoined",
))
_OUTCOME_REQUIRED = frozenset(
    ("transport", "target", "dispatch", "wake", "receipt", "response")
)
_OUTCOME_OPTIONAL = frozenset(("routeReason", "fallbackFrom", "nextStep"))
_TARGET_FIELDS = frozenset(("host", "name", "project"))


class RoutingError(ValueError):
    """Trusted routing facts or public state violate the contract."""


def _exact_fields(value: object, required: frozenset[str], optional: frozenset[str] = frozenset(),
                  *, label: str = "input") -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise RoutingError(label + ": object required")
    fields = frozenset(value)
    missing = sorted(required - fields)
    if missing:
        raise RoutingError(label + ": missing-fields: " + ", ".join(missing))
    unexpected = sorted(fields - required - optional)
    if unexpected:
        raise RoutingError(label + ": unexpected-fields: " + ", ".join(unexpected))
    return value


def _enum(value: object, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise RoutingError(label + ": invalid value")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise RoutingError(label + ": boolean required")
    return value


def _text(value: object, label: str, *, maximum: int) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise RoutingError(label + ": invalid text")
    return value


def _primary_transport(host: str, target: str) -> str:
    if host != target:
        return "spec-guard-bridge"
    return "host-native-" + host


def _decision(action: str, transport: str, reason: str,
              *, fallback_from: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "action": action,
        "transport": transport,
        "routeReason": reason,
    }
    if fallback_from is not None:
        result["fallbackFrom"] = fallback_from
    return result


def select_route(facts: object) -> dict[str, object]:
    """Return one route decision from trusted capability and bridge facts."""
    values = _exact_fields(facts, _ROUTE_FIELDS)
    origin = _enum(values["originHost"], HOSTS, "originHost")
    target = _enum(values["targetHost"], HOSTS, "targetHost")
    authorization = _enum(
        values["authorizationState"], AUTHORIZATION_STATES, "authorizationState"
    )
    resolution = _enum(values["targetResolution"], TARGET_RESOLUTIONS, "targetResolution")
    capability = _enum(
        values["nativeCapability"], NATIVE_CAPABILITIES, "nativeCapability"
    )
    native_dispatch = _enum(
        values["nativeDispatch"], NATIVE_DISPATCHES, "nativeDispatch"
    )
    bridge = _enum(values["bridgeState"], BRIDGE_STATES, "bridgeState")
    origin_joined = _boolean(values["originJoined"], "originJoined")
    target_joined = _boolean(values["targetJoined"], "targetJoined")
    primary = _primary_transport(origin, target)

    same_host = origin == target
    if same_host:
        if capability == "not-applicable":
            raise RoutingError("nativeCapability: inconsistent same-host fact")
        if capability != "available" and native_dispatch != "not-attempted":
            raise RoutingError("nativeDispatch: result without available capability")
    else:
        if capability != "not-applicable" or native_dispatch != "not-attempted":
            raise RoutingError("nativeCapability: cross-host native facts are not applicable")

    if authorization != "authorized":
        return _decision(
            "stop", primary,
            "authorization-required" if authorization == "unauthorized"
            else "authorization-unknown",
        )
    if resolution != "unique":
        return _decision("stop", primary, "target-" + resolution)

    if not same_host:
        if bridge != "ready":
            return _decision("stop", primary, "bridge-" + bridge)
        if not origin_joined:
            return _decision("stop", primary, "origin-not-joined")
        if not target_joined:
            return _decision("stop", primary, "target-not-joined")
        return _decision("dispatch", primary, "cross-host-bridge")

    if capability == "available":
        if native_dispatch == "not-attempted":
            return _decision("dispatch", primary, "primary-native")
        if native_dispatch == "accepted":
            return _decision("observe", primary, "native-dispatch-accepted")
        if native_dispatch == "unknown":
            return _decision("reconcile", primary, "native-dispatch-unknown")
        return _decision("stop", primary, "native-dispatch-rejected")

    if capability == "unknown":
        return _decision("reconcile", primary, "native-capability-unknown")

    if bridge != "ready":
        return _decision("stop", primary, "native-unavailable-bridge-" + bridge)
    if not origin_joined:
        return _decision("stop", primary, "native-unavailable-origin-not-joined")
    if not target_joined:
        return _decision("stop", primary, "native-unavailable-target-not-joined")
    return _decision(
        "dispatch", "spec-guard-bridge", "native-capability-unavailable",
        fallback_from=primary,
    )


def _validate_target(value: object) -> None:
    target = _exact_fields(value, _TARGET_FIELDS, label="target")
    _enum(target["host"], HOSTS, "target.host")
    _text(target["name"], "target.name", maximum=120)
    project = _text(target["project"], "target.project", maximum=120)
    if project in (".", "..") or "/" in project or "\\" in project:
        raise RoutingError("target.project: basename required")


def validate_public_outcome(outcome: object) -> dict[str, object]:
    """Validate and return a public outcome without strengthening its evidence."""
    values = _exact_fields(outcome, _OUTCOME_REQUIRED, _OUTCOME_OPTIONAL, label="outcome")
    transport = _enum(values["transport"], TRANSPORTS, "transport")
    _validate_target(values["target"])
    dispatch = _enum(values["dispatch"], DISPATCH_STATES, "dispatch")
    wake = _enum(values["wake"], WAKE_STATES, "wake")
    receipt = _enum(values["receipt"], RECEIPT_STATES, "receipt")
    response = _enum(values["response"], RESPONSE_STATES, "response")

    proven_dispatch = dispatch in ("accepted", "enqueued", "held")
    if not proven_dispatch and (
        wake in ("admitted", "held")
        or receipt in ("delivered", "read", "acknowledged")
        or response in ("pending", "received")
    ):
        raise RoutingError("state-evidence: outcome exceeds dispatch evidence")

    for field in ("routeReason", "nextStep"):
        if field in values:
            _text(values[field], field, maximum=240)

    fallback = values.get("fallbackFrom")
    if fallback is not None:
        fallback = _enum(
            fallback,
            frozenset(("host-native-claude", "host-native-codex")),
            "fallbackFrom",
        )
        if transport != "spec-guard-bridge":
            raise RoutingError("fallbackFrom: bridge transport required")
        if "routeReason" not in values:
            raise RoutingError("fallbackFrom: routeReason required")
    return dict(values)


def _read_json() -> object:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise RoutingError("input: invalid JSON") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("select", "validate-outcome"))
    args = parser.parse_args(argv)
    try:
        payload = _read_json()
        result = (select_route(payload) if args.command == "select"
                  else validate_public_outcome(payload))
    except RoutingError as error:
        print(json.dumps({"state": "error", "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
