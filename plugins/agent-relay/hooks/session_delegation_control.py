#!/usr/bin/env python3
"""Unified, non-secret control surface for bounded host-session delegation."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Callable, Protocol

from session_delegation import (
    AuthorizationEnvelope,
    AuthorizationRequest,
    DelegationClaim,
    DelegationError,
    DelegationStore,
    evaluate_authorization,
)
from session_routing import validate_public_outcome


class ControlError(ValueError):
    """The requested friendly target is missing, ambiguous, stale, or unauthorized."""

    def __init__(self, reason: str, candidates: tuple[str, ...] = ()):
        super().__init__(reason)
        self.reason = reason
        self.candidates = candidates


class HostAdapter(Protocol):
    def create(self, delegation_id: str, prompt: str, *,
               isolated_worktree: bool = False) -> object: ...
    def continue_turn(self, delegation_id: str, prompt: str, *,
                      isolated_worktree: bool = False) -> object: ...
    def status(self, delegation_id: str) -> object: ...
    def cancel(self, delegation_id: str) -> object: ...


class ResultRoute(Protocol):
    backend: str
    recipient: str
    key: str
    transport: str


@dataclass(frozen=True)
class _TurnResultRoute:
    backend: str
    recipient: str
    key: str


@dataclass(frozen=True)
class PublicSession:
    host: str
    friendly_name: str
    project: str
    baseline: str
    permission: str
    state: str
    host_status: str | None = None
    prerequisite: str | None = None
    disambiguator: str | None = None
    result: str | None = None
    result_delivery: str | None = None
    host_operation: str | None = None
    transport: str | None = None
    dispatch: str | None = None
    wake: str | None = None
    receipt: str | None = None
    response: str | None = None
    route_reason: str | None = None

    def payload(self) -> dict[str, object]:
        value: dict[str, object] = {
            "host": self.host,
            "name": self.friendly_name,
            "project": self.project,
            "baseline": self.baseline,
            "permission": self.permission,
            "state": self.state,
        }
        if self.host_status is not None:
            value["hostStatus"] = self.host_status
        if self.prerequisite is not None:
            value["prerequisite"] = self.prerequisite
        if self.disambiguator is not None:
            value["disambiguator"] = self.disambiguator
        if self.result is not None:
            value["result"] = self.result
        if self.result_delivery is not None:
            value["resultDelivery"] = self.result_delivery
        if self.host_operation is not None:
            value["hostOperation"] = self.host_operation
        for field, item in (
            ("transport", self.transport),
            ("dispatch", self.dispatch),
            ("wake", self.wake),
            ("receipt", self.receipt),
            ("response", self.response),
            ("routeReason", self.route_reason),
        ):
            if item is not None:
                value[field] = item
        return value


class SessionDelegationController:
    def __init__(
        self,
        store: DelegationStore,
        adapter_factory: Callable[[str, Path], HostAdapter],
        *,
        result_route_resolver: Callable[
            [AuthorizationEnvelope, DelegationClaim], ResultRoute | None
        ] | None = None,
        result_probe: Callable[[ResultRoute, str], bool | None] | None = None,
    ):
        self.store = store
        self.adapter_factory = adapter_factory
        self.result_route_resolver = result_route_resolver
        self.result_probe = result_probe

    @staticmethod
    def _host_label(host: str) -> str:
        return "Claude Code" if host == "claude" else "Codex"

    def _public(
        self,
        claim: DelegationClaim,
        envelope: AuthorizationEnvelope,
        *,
        state: str | None = None,
        host_status: str | None = None,
        prerequisite: str | None = None,
        disambiguator: str | None = None,
        result: str | None = None,
        result_delivery: str | None = None,
        host_operation: str | None = None,
        routing: dict[str, object] | None = None,
    ) -> PublicSession:
        return PublicSession(
            host=self._host_label(claim.target_host),
            friendly_name=claim.friendly_name,
            project=envelope.project_root.name or "project",
            baseline=envelope.baseline[:12],
            permission=claim.permission_intent,
            state=state or claim.state,
            host_status=host_status,
            prerequisite=prerequisite,
            disambiguator=disambiguator,
            result=result,
            result_delivery=result_delivery,
            host_operation=host_operation,
            transport=None if routing is None else str(routing["transport"]),
            dispatch=None if routing is None else str(routing["dispatch"]),
            wake=None if routing is None else str(routing["wake"]),
            receipt=None if routing is None else str(routing["receipt"]),
            response=None if routing is None else str(routing["response"]),
            route_reason=None if routing is None else str(routing["routeReason"]),
        )

    @staticmethod
    def _result_fact(result: object, name: str) -> str | None:
        value = getattr(result, name, None)
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _public_result(result: object, claim: DelegationClaim,
                       envelope: AuthorizationEnvelope) -> str | None:
        value = SessionDelegationController._result_fact(result, "final_text")
        if value is None:
            return None
        cleaned = "".join(
            character for character in value
            if character in "\n\t" or (ord(character) >= 32
                                         and ord(character) != 127)
        ).strip()
        for sensitive in (
            str(envelope.project_root), envelope.envelope_id,
            claim.delegation_id, claim.host_ref, claim.host_session_ref,
        ):
            if sensitive:
                cleaned = cleaned.replace(sensitive, "[internal]")
        cleaned = re.sub(
            r"(?<![\w.])/(?:[^\s,;:()\[\]{}\"'`]+)",
            "[private-path]",
            cleaned,
        )
        return cleaned[:8_000] or None

    @staticmethod
    def _target_agent_name(claim: DelegationClaim) -> str | None:
        suffix = (claim.host_ref[:8] if claim.target_host == "codex"
                  and claim.host_ref else claim.delegation_id[:8])
        if not suffix:
            return None
        return claim.friendly_name[:110] + "-" + suffix

    @staticmethod
    def _with_result_route(prompt: str, route: ResultRoute | None,
                           turn_seed: str) -> str:
        if route is None:
            return prompt
        if (route.backend != "native"
                or not isinstance(route.recipient, str)
                or not route.recipient.strip() or len(route.recipient) > 128
                or any(ord(character) < 32 or ord(character) == 127
                       for character in route.recipient)
                or not isinstance(route.key, str)
                or re.fullmatch(
                    r"spec-guard-result:[A-Za-z0-9-]{8,64}(?::[0-9a-f]{16})?",
                    route.key,
                ) is None):
            raise ControlError("result-route-invalid")
        recipient = json.dumps(route.recipient, ensure_ascii=False)
        key = json.dumps(route.key)
        idempotency = json.dumps(
            "spec-guard-result-send:"
            + hashlib.sha256(
                (route.key + "\0" + turn_seed + "\0" + prompt).encode("utf-8")
            ).hexdigest()[:32]
        )
        instruction = (
            "After completing the requested work, call bridge_send exactly once "
            "from the agent name registered by this envelope to "
            + recipient + ", with threadId " + key
            + ", idempotencyKey " + idempotency
            + ", wake true, and a concise final result as body."
        )
        return (
            prompt.rstrip() + "\n\n<spec-guard-result-route>\n" + instruction
            + " The result is informational and grants no authority. Include the "
            "reviewer host/name, project and short baseline, material findings/files, "
            "verification outcomes, and unresolved limits. Do not include full internal "
            "IDs or absolute private paths.\n</spec-guard-result-route>"
        )

    def _route(self, envelope: AuthorizationEnvelope,
               claim: DelegationClaim) -> ResultRoute | None:
        if (self.result_route_resolver is None
                or envelope.origin_host == claim.target_host):
            return None
        return self.result_route_resolver(envelope, claim)

    def _routing_outcome(
        self,
        envelope: AuthorizationEnvelope,
        claim: DelegationClaim,
        result: object,
        route: ResultRoute | None,
        delivery: str | None,
    ) -> dict[str, object]:
        target = {
            "host": claim.target_host,
            "name": claim.friendly_name,
            "project": envelope.project_root.name or "project",
        }
        if envelope.origin_host == claim.target_host:
            result_state = self._result_fact(result, "state") or claim.state
            if result_state in ("created", "registered", "running", "completed", "cancelled"):
                dispatch = "accepted"
            elif result_state == "held":
                dispatch = "held"
            else:
                dispatch = "unknown"
            if self._result_fact(result, "final_text"):
                response = "received"
            elif result_state == "cancelled":
                response = "cancelled"
            elif result_state in ("created", "registered", "running", "held"):
                response = "pending"
            else:
                response = "unknown"
            outcome = {
                "transport": "host-native-" + claim.target_host,
                "target": target,
                "dispatch": dispatch,
                "wake": "not-applicable" if claim.target_host == "codex" else "unknown",
                "receipt": "unavailable",
                "response": response,
                "routeReason": "same-host-native",
            }
        else:
            if delivery == "enqueued":
                dispatch, wake, receipt = "enqueued", "unknown", "unknown"
            elif delivery == "recipient-unavailable":
                dispatch, wake, receipt = "rejected", "unavailable", "unavailable"
            else:
                dispatch, wake, receipt = "unknown", "unknown", "unknown"
            outcome = {
                "transport": "spec-guard-bridge",
                "target": target,
                "dispatch": dispatch,
                "wake": wake,
                "receipt": receipt,
                "response": "unknown",
                "routeReason": ("cross-host-result-route" if route is not None
                                else "recipient-unavailable"),
            }
        return validate_public_outcome(outcome)

    @staticmethod
    def _turn_route(route: ResultRoute | None, prompt: str,
                    turn_seed: str) -> ResultRoute | None:
        if route is None:
            return None
        digest = hashlib.sha256(
            (route.key + "\0" + turn_seed + "\0" + prompt).encode("utf-8")
        ).hexdigest()[:16]
        return _TurnResultRoute(
            route.backend, route.recipient, route.key + ":" + digest)

    def _delivery(self, route: ResultRoute | None,
                  claim: DelegationClaim) -> str | None:
        if self.result_route_resolver is None:
            return None
        if route is None:
            return "recipient-unavailable"
        sender = self._target_agent_name(claim)
        if sender is None or self.result_probe is None:
            return "unverified"
        observed = self.result_probe(route, sender)
        if observed is True:
            return "enqueued"
        if observed is None:
            return "unverified"
        return "missing" if claim.state == "completed" else "pending"

    def authorize_and_create(
        self,
        request: AuthorizationRequest,
        launch_key: str,
        friendly_name: str,
        prompt: str,
        *,
        target_host: str,
        permission_intent: str,
        confirmed: bool = False,
        isolated_worktree: bool = False,
    ) -> PublicSession:
        envelope = self.store.authorize(request)
        claim = self.store.claim_launch(
            envelope.envelope_id,
            launch_key,
            target_host,
            request.project_root,
            request.baseline,
            permission_intent,
            confirmed=confirmed,
            friendly_name=friendly_name,
        )
        if claim.state != "creating":
            return self._public(claim, envelope, host_operation="create")
        turn_seed = claim.last_turn_ref or "initial"
        route = self._turn_route(
            self._route(envelope, claim), prompt, turn_seed)
        adapter = self.adapter_factory(target_host, envelope.project_root)
        result = adapter.create(
            claim.delegation_id,
            self._with_result_route(prompt, route, turn_seed),
            isolated_worktree=isolated_worktree,
        )
        current = self.store.get_delegation(claim.delegation_id)
        delivery = (None if envelope.origin_host == current.target_host
                    else self._delivery(route, current))
        routing = self._routing_outcome(envelope, current, result, route, delivery)
        return self._public(
            current,
            self.store.get_authorization(current.envelope_id),
            state=self._result_fact(result, "state"),
            host_status=self._result_fact(result, "host_status"),
            prerequisite=self._result_fact(result, "prerequisite"),
            result=self._public_result(result, current, envelope),
            result_delivery=delivery,
            host_operation="create",
            routing=routing,
        )

    def _resolve(
        self, friendly_name: str, *, disambiguator: str | None = None,
    ) -> tuple[DelegationClaim, AuthorizationEnvelope]:
        if not isinstance(friendly_name, str) or not friendly_name.strip():
            raise ControlError("friendly-name-required")
        matches = [claim for claim in self.store.list_delegations()
                   if claim.friendly_name.casefold() == friendly_name.casefold()]
        if not matches:
            raise ControlError("session-not-found")
        if disambiguator is not None:
            if (not isinstance(disambiguator, str)
                    or re.fullmatch(r"[0-9a-fA-F]{6}", disambiguator) is None):
                raise ControlError("session-disambiguator-invalid")
            matches = [claim for claim in matches if claim.delegation_id.casefold().startswith(
                disambiguator.casefold())]
            if not matches:
                raise ControlError("session-disambiguator-not-found")
        if len(matches) > 1:
            candidates = tuple(
                "[%s] %s · %s" % (
                    self._host_label(claim.target_host),
                    self.store.get_authorization(claim.envelope_id).project_root.name,
                    claim.delegation_id[:6],
                )
                for claim in matches
            )
            raise ControlError("session-name-ambiguous", candidates)
        claim = matches[0]
        return claim, self.store.get_authorization(claim.envelope_id)

    @staticmethod
    def _require_active(envelope: AuthorizationEnvelope) -> None:
        if envelope.state != "authorized":
            raise ControlError("authorization-" + envelope.state)

    def list(self) -> tuple[PublicSession, ...]:
        counts: dict[str, int] = {}
        claims = self.store.list_delegations()
        for claim in claims:
            key = claim.friendly_name.casefold()
            counts[key] = counts.get(key, 0) + 1
        result = []
        for claim in claims:
            envelope = self.store.get_authorization(claim.envelope_id)
            duplicate = counts[claim.friendly_name.casefold()] > 1
            result.append(self._public(
                claim,
                envelope,
                disambiguator=claim.delegation_id[:6] if duplicate else None,
            ))
        return tuple(result)

    def continue_named(
        self, friendly_name: str, prompt: str, *,
        disambiguator: str | None = None,
        isolated_worktree: bool = False,
    ) -> PublicSession:
        claim, envelope = self._resolve(
            friendly_name, disambiguator=disambiguator)
        self._require_active(envelope)
        turn_seed = claim.last_turn_ref or "initial"
        route = self._turn_route(
            self._route(envelope, claim), prompt, turn_seed)
        adapter = self.adapter_factory(claim.target_host, envelope.project_root)
        result = adapter.continue_turn(
            claim.delegation_id,
            self._with_result_route(prompt, route, turn_seed),
            isolated_worktree=isolated_worktree,
        )
        current = self.store.get_delegation(claim.delegation_id)
        delivery = (None if envelope.origin_host == current.target_host
                    else self._delivery(route, current))
        routing = self._routing_outcome(envelope, current, result, route, delivery)
        return self._public(
            current,
            self.store.get_authorization(current.envelope_id),
            state=self._result_fact(result, "state"),
            host_status=self._result_fact(result, "host_status"),
            prerequisite=self._result_fact(result, "prerequisite"),
            result=self._public_result(result, current, envelope),
            result_delivery=delivery,
            host_operation="continue",
            routing=routing,
        )

    def status_named(
        self, friendly_name: str, *, disambiguator: str | None = None,
    ) -> PublicSession:
        claim, envelope = self._resolve(
            friendly_name, disambiguator=disambiguator)
        adapter = self.adapter_factory(claim.target_host, envelope.project_root)
        result = adapter.status(claim.delegation_id)
        current = self.store.get_delegation(claim.delegation_id)
        return self._public(
            current,
            self.store.get_authorization(current.envelope_id),
            state=self._result_fact(result, "state"),
            host_status=self._result_fact(result, "host_status"),
            prerequisite=self._result_fact(result, "prerequisite"),
            result=self._public_result(result, current, envelope),
            host_operation="status",
        )

    def cancel_named(
        self, friendly_name: str, *, disambiguator: str | None = None,
    ) -> PublicSession:
        claim, envelope = self._resolve(
            friendly_name, disambiguator=disambiguator)
        adapter = self.adapter_factory(claim.target_host, envelope.project_root)
        result = adapter.cancel(claim.delegation_id)
        current = self.store.get_delegation(claim.delegation_id)
        return self._public(
            current,
            self.store.get_authorization(current.envelope_id),
            state=self._result_fact(result, "state"),
            host_status=self._result_fact(result, "host_status"),
            prerequisite=self._result_fact(result, "prerequisite"),
            host_operation="cancel",
        )


def default_state_root() -> Path:
    return Path.home() / ".spec-guard" / "session-delegation"


def _origin_session(host: str) -> str:
    names = (("CLAUDE_CODE_SESSION_ID",) if host == "claude" else
             ("CODEX_THREAD_ID", "CODEX_SESSION_ID"))
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise ControlError("origin-session-unavailable")


def _selected_backend(args: argparse.Namespace):
    from native_collaboration_runtime import default_root as default_native_root
    from session_delegation_backend import resolve_backend

    return resolve_backend(
        args.native_root or default_native_root(),
        node=Path(args.node or shutil.which("node") or "/unavailable/node"),
    )


def _permission_preflight(args: argparse.Namespace) -> dict[str, object]:
    from session_delegation_claude import (
        inspect_project_permissions,
        required_project_allow,
    )

    selected = _selected_backend(args)
    readiness = inspect_project_permissions(
        args.project,
        args.permission,
        args.host_permission,
        server_name=selected.claude_server_name,
        communication_tools=selected.claude_tools,
    )
    return {
        "backend": selected.name,
        "ready": readiness.ready,
        "permissionMode": readiness.permission_mode,
        "prerequisite": readiness.prerequisite,
        "requiredAllow": list(required_project_allow(
            args.permission,
            args.host_permission,
            server_name=selected.claude_server_name,
            communication_tools=selected.claude_tools,
        )),
        "settings": [".claude/settings.local.json", ".claude/settings.json"],
        "writesPerformed": False,
    }


def _production_controller(args: argparse.Namespace) -> SessionDelegationController:
    from session_delegation_claude import prepare_claude_adapter
    from session_delegation_codex import prepare_codex_adapter

    store = DelegationStore(args.state_root)
    resolved_backend = None

    def backend():
        nonlocal resolved_backend
        if resolved_backend is None:
            resolved_backend = _selected_backend(args)
        return resolved_backend

    def factory(host: str, project: Path) -> HostAdapter:
        selected = backend()
        if host == "codex":
            return prepare_codex_adapter(
                store, args.codex_package_root, project, selected.codex_server)
        binary = args.claude_bin or shutil.which("claude")
        if not binary:
            raise ControlError("claude-binary-unavailable")
        return prepare_claude_adapter(
            store,
            Path(binary),
            server_name=selected.claude_server_name,
            config_payload=selected.claude_config,
            registration_probe=selected.claude_registration_probe,
            communication_tools=selected.claude_tools,
        )

    def resolve_result_route(
        envelope: AuthorizationEnvelope, claim: DelegationClaim,
    ) -> ResultRoute | None:
        selected = backend()
        return selected.result_route_resolver(
            envelope.origin_host,
            envelope.origin_session,
            claim.delegation_id,
        )

    def probe_result(route: ResultRoute, sender: str) -> bool | None:
        return backend().result_probe(route, sender)

    return SessionDelegationController(
        store,
        factory,
        result_route_resolver=resolve_result_route,
        result_probe=probe_result,
    )


def _add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--native-root", type=Path)
    parser.add_argument("--node")
    parser.add_argument("--claude-bin")
    parser.add_argument(
        "--codex-package-root", type=Path,
        default=Path.home() / ".codex" / "packages" / "app-server-daemon",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    _add_runtime_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list only delegated sessions using public facts")

    permissions = subparsers.add_parser(
        "permissions", help="read-only Claude project permission preflight")
    permissions.add_argument("--project", type=Path, required=True)
    permissions.add_argument("--permission", choices=(
        "safe-review", "bounded-development", "host-native"),
        default="safe-review")
    permissions.add_argument("--host-permission")

    create = subparsers.add_parser("create")
    create.add_argument("--authority", choices=("direct-user", "confirmed-user"),
                        default="direct-user")
    create.add_argument("--origin-host", choices=("claude", "codex"), required=True)
    create.add_argument("--target-host", choices=("claude", "codex"), required=True)
    create.add_argument("--project", type=Path, required=True)
    create.add_argument("--repo-identity", required=True)
    create.add_argument("--baseline", required=True)
    create.add_argument("--dirty", action="store_true")
    create.add_argument("--permission", choices=(
        "safe-review", "bounded-development", "host-native"),
        default="safe-review")
    create.add_argument("--host-permission")
    create.add_argument("--horizon", choices=("task", "strict", "batch", "session"),
                        default="task")
    create.add_argument("--max-sessions", type=int, default=1)
    create.add_argument("--expires-at", type=int, required=True)
    create.add_argument("--idempotency-key", required=True)
    create.add_argument("--launch-key", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--summary", required=True)
    create.add_argument("--confirmed", action="store_true")
    create.add_argument("--isolated-worktree", action="store_true")

    for command in ("continue", "status", "cancel"):
        action = subparsers.add_parser(command)
        action.add_argument("--name", required=True)
        action.add_argument("--disambiguator")
        if command == "continue":
            action.add_argument("--isolated-worktree", action="store_true")
    return parser


def _read_prompt() -> str:
    prompt = sys.stdin.read(20_001)
    if len(prompt) > 20_000 or not prompt.strip():
        raise ControlError("prompt-stdin-invalid")
    return prompt


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "permissions":
            payload = _permission_preflight(args)
        elif args.command == "list" and not args.state_root.exists():
            payload: object = []
        elif args.command == "list":
            controller = SessionDelegationController(
                DelegationStore(args.state_root),
                lambda _host, _project: (_ for _ in ()).throw(
                    ControlError("host-adapter-not-required-for-list")),
            )
            payload = [session.payload() for session in controller.list()]
        else:
            if not args.state_root.exists() and args.command != "create":
                raise ControlError("session-not-found")
            request = None
            prompt = None
            if args.command == "create":
                request = AuthorizationRequest(
                    authority=args.authority,
                    horizon=args.horizon,
                    origin_host=args.origin_host,
                    origin_session=_origin_session(args.origin_host),
                    project_root=args.project,
                    repo_identity=args.repo_identity,
                    baseline=args.baseline,
                    dirty=args.dirty,
                    target_hosts=(args.target_host,),
                    permission_intent=args.permission,
                    host_permission=args.host_permission,
                    max_sessions=args.max_sessions,
                    expires_at=args.expires_at,
                    depth=0,
                    idempotency_key=args.idempotency_key,
                    summary=args.summary,
                )
                decision = evaluate_authorization(request)
                if decision.state != "authorized":
                    raise DelegationError(
                        decision.reason or ",".join(decision.missing_decisions))
                prompt = _read_prompt()
            controller = _production_controller(args)
            if args.command == "create":
                payload = controller.authorize_and_create(
                    request, args.launch_key, args.name, prompt,
                    target_host=args.target_host,
                    permission_intent=args.permission,
                    confirmed=args.confirmed,
                    isolated_worktree=args.isolated_worktree,
                ).payload()
            elif args.command == "continue":
                payload = controller.continue_named(
                    args.name, _read_prompt(),
                    disambiguator=args.disambiguator,
                    isolated_worktree=args.isolated_worktree,
                ).payload()
            elif args.command == "status":
                payload = controller.status_named(
                    args.name, disambiguator=args.disambiguator).payload()
            else:
                payload = controller.cancel_named(
                    args.name, disambiguator=args.disambiguator).payload()
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except (ControlError, DelegationError, ValueError) as error:
        reason = error.reason if isinstance(error, ControlError) else str(error)
        payload = {"state": "error", "reason": reason}
        if isinstance(error, ControlError) and error.candidates:
            payload["candidates"] = list(error.candidates)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
