#!/usr/bin/env python3
"""Unified, non-secret control surface for bounded host-session delegation."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
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
        return value


class SessionDelegationController:
    def __init__(
        self,
        store: DelegationStore,
        adapter_factory: Callable[[str, Path], HostAdapter],
    ):
        self.store = store
        self.adapter_factory = adapter_factory

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
    ) -> PublicSession:
        return PublicSession(
            self._host_label(claim.target_host),
            claim.friendly_name,
            envelope.project_root.name or "project",
            envelope.baseline[:12],
            claim.permission_intent,
            state or claim.state,
            host_status,
            prerequisite,
            disambiguator,
        )

    @staticmethod
    def _result_fact(result: object, name: str) -> str | None:
        value = getattr(result, name, None)
        return value if isinstance(value, str) and value else None

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
            return self._public(claim, envelope)
        adapter = self.adapter_factory(target_host, envelope.project_root)
        result = adapter.create(
            claim.delegation_id, prompt,
            isolated_worktree=isolated_worktree,
        )
        current = self.store.get_delegation(claim.delegation_id)
        return self._public(
            current,
            self.store.get_authorization(current.envelope_id),
            state=self._result_fact(result, "state"),
            host_status=self._result_fact(result, "host_status"),
            prerequisite=self._result_fact(result, "prerequisite"),
        )

    def _resolve(self, friendly_name: str) -> tuple[DelegationClaim, AuthorizationEnvelope]:
        if not isinstance(friendly_name, str) or not friendly_name.strip():
            raise ControlError("friendly-name-required")
        matches = [claim for claim in self.store.list_delegations()
                   if claim.friendly_name.casefold() == friendly_name.casefold()]
        if not matches:
            raise ControlError("session-not-found")
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
        isolated_worktree: bool = False,
    ) -> PublicSession:
        claim, envelope = self._resolve(friendly_name)
        self._require_active(envelope)
        adapter = self.adapter_factory(claim.target_host, envelope.project_root)
        result = adapter.continue_turn(
            claim.delegation_id, prompt,
            isolated_worktree=isolated_worktree,
        )
        current = self.store.get_delegation(claim.delegation_id)
        return self._public(
            current,
            self.store.get_authorization(current.envelope_id),
            state=self._result_fact(result, "state"),
            host_status=self._result_fact(result, "host_status"),
            prerequisite=self._result_fact(result, "prerequisite"),
        )

    def status_named(self, friendly_name: str) -> PublicSession:
        claim, envelope = self._resolve(friendly_name)
        adapter = self.adapter_factory(claim.target_host, envelope.project_root)
        result = adapter.status(claim.delegation_id)
        current = self.store.get_delegation(claim.delegation_id)
        return self._public(
            current,
            self.store.get_authorization(current.envelope_id),
            state=self._result_fact(result, "state"),
            host_status=self._result_fact(result, "host_status"),
            prerequisite=self._result_fact(result, "prerequisite"),
        )

    def cancel_named(self, friendly_name: str) -> PublicSession:
        claim, envelope = self._resolve(friendly_name)
        adapter = self.adapter_factory(claim.target_host, envelope.project_root)
        result = adapter.cancel(claim.delegation_id)
        current = self.store.get_delegation(claim.delegation_id)
        return self._public(
            current,
            self.store.get_authorization(current.envelope_id),
            state=self._result_fact(result, "state"),
            host_status=self._result_fact(result, "host_status"),
            prerequisite=self._result_fact(result, "prerequisite"),
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


def _production_controller(args: argparse.Namespace) -> SessionDelegationController:
    from collaboration_backend import default_marker
    from collaboration_runtime import default_config_dir
    from native_collaboration_runtime import default_root as default_native_root
    from session_delegation_backend import resolve_backend
    from session_delegation_claude import prepare_claude_adapter
    from session_delegation_codex import prepare_codex_adapter

    store = DelegationStore(args.state_root)
    plugin_root = Path(__file__).resolve().parent
    resolved_backend = None

    def backend():
        nonlocal resolved_backend
        if resolved_backend is None:
            resolved_backend = resolve_backend(
                args.marker or default_marker(),
                args.native_root or default_native_root(),
                args.xats_config_dir or default_config_dir(),
                node=Path(args.node or shutil.which("node") or "/unavailable/node"),
                npx=Path(args.npx or shutil.which("npx") or "/unavailable/npx"),
                python_executable=Path(sys.executable),
                header_helper=plugin_root / "collaboration_auth_header.py",
                stdio_helper=plugin_root / "collaboration_claude_stdio.py",
            )
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
            args.xats_config_dir or default_config_dir(),
            server_name=selected.claude_server_name,
            config_payload=selected.claude_config,
            registration_probe=selected.claude_registration_probe,
        )

    return SessionDelegationController(store, factory)


def _add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--native-root", type=Path)
    parser.add_argument("--xats-config-dir", type=Path)
    parser.add_argument("--node")
    parser.add_argument("--npx")
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
        if args.command == "list" and not args.state_root.exists():
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
                    isolated_worktree=args.isolated_worktree,
                ).payload()
            elif args.command == "status":
                payload = controller.status_named(args.name).payload()
            else:
                payload = controller.cancel_named(args.name).payload()
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
