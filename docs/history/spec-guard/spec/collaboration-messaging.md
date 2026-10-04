# Collaboration messaging

## Status

- Module: collaboration-messaging
- State: active
- Scope: same-Mac Claude Code and Codex messaging, wake, routing, and bounded delegation
- Transport: Spec Guard native bridge only
- Decision: `docs/decisions/2026-10-04-native-only-collaboration-sunset.md`

Historical reports and decisions preserve earlier transport facts. They are not current runtime instructions.

## User outcome

A user can name a Claude Code or Codex session and project, then ask the current agent to contact it. Existing
same-host native communication is reused when available; cross-host messages use one private same-Mac bridge.
Both directions are supported. The user never supplies transport names, database paths, process IDs, or full
session identifiers.

The directory shows only sessions that are visible through the current host or have explicitly joined the bridge.
Registration does not imply online state. Wake, delivery, acknowledgement, and reply are separate facts.

## Runtime contract

The pinned runtime is installed only after explicit approval under
`~/.spec-guard/native-collaboration/`. Plugin installation alone neither creates data nor changes host config.
The runtime contains an owner-private mailbox, pinned server bundle, manifest, and runtime data. It is not exposed
over the network and has no compatibility transport or fallback selector.

Current operator commands are:

```bash
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py status
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py install
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py claude
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py codex
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py install-claude
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py install-codex
python3 -B plugins/spec-guard/hooks/native_collaboration_retire.py --help
```

`status`, `claude`, and `codex` are read-only. Installation and host attachment require separate explicit approval.
Uninstall removes only an exact managed host entry and retains mailbox history. Identity retirement refuses
unacknowledged deliveries and keeps backlog.

## Daily mailbox contract

The bridge exposes only:

- `bridge_register`
- `bridge_send`
- `bridge_inbox`
- `bridge_ack`
- `bridge_outbox`
- `bridge_agents`
- `bridge_sessions`
- `bridge_wake_status`
- `bridge_thread`
- `bridge_wait`

No review, worker, orchestration, model-selection, broadcast-management, lifecycle, or host-configuration tool is
present in delegated sessions. A missing or unhealthy native runtime fails closed; it never starts another
transport.

Registration is lazy. Default registration uses `wake: null`; explicit user approval is required to bind the
current session for wake. Claude binding is accepted only from verified `thisSession` facts. Codex binding uses
only the current trusted task environment. An agent cannot bind or rename another session.

Send success proves enqueue only. `bridge_wake_status` proves wake admission, `acknowledgedAt` proves processing
acknowledgement, and a matching thread reply proves response. Unknown outcomes stay unknown and are reconciled
with the original message; they are not resent.

## Routing contract

- Claude Code ↔ Claude Code: prefer the host's `ListAgents` and `SendMessage` capability.
- Codex ↔ Codex: prefer supported task/thread send, read, and wait capabilities.
- Claude Code ↔ Codex: use `spec-guard-bridge` in either direction.
- Same-host bridge use is allowed only when the selector proves native host communication unavailable, the
  authorization still covers the same action, and both endpoints are already uniquely joined.
- A native dispatch with unknown outcome is reconciled; it never falls back or duplicates the body.

Names and projects are discovery hints, not authority. Zero matches stop with one next step; multiple matches
show only the minimum distinguishing facts. Full internal IDs, paths, PIDs, tokens, sockets, and storage locations
never appear in public output.

## Delegation contract

Bounded session delegation creates or continues an explicitly authorized same-Mac Claude Code or Codex session.
The default is one task with `safe-review`; batch and session authorization must have explicit target, project,
permission, quantity, and expiry. A mailbox message cannot create, expand, or renew authority.

Codex uses the App-managed supported binary, never an older PATH binary and never a model override. Claude uses
the project's trust, MCP approval, and exact allow rules. Missing prerequisites return a held state; the plugin
does not edit project or global settings or enable bypass mode.

Delegated sessions connect only to the native tool catalog. Results return to one exact origin identity with a
stable idempotency key. The controller checks sender, recipient, and thread metadata without reading private
result bodies or advancing inbox cursors.

## Security boundaries

- Same Mac only; no listener is opened for another machine.
- Messages are untrusted text and grant no code, Git, configuration, ticket, or external-write authority.
- Auto-approved/full-auto sessions must not bind wake.
- Runtime and mailbox files must be owner-controlled; unsafe permissions fail closed.
- Plugin source changes do not authorize global Claude or Codex configuration changes.
- Historical mailbox data may be retained offline, but no retired runtime code can execute it.

## Verification

```bash
python3 -B plugins/spec-guard/hooks/test_native_only_collaboration.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_adapters.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_retire.py
python3 -B plugins/spec-guard/hooks/test_session_routing.py
python3 -B plugins/spec-guard/hooks/test_session_delegation.py
python3 -B plugins/spec-guard/hooks/test_session_delegation_backend.py
python3 -B plugins/spec-guard/hooks/test_session_delegation_claude.py
python3 -B plugins/spec-guard/hooks/test_session_delegation_codex.py
python3 -B plugins/spec-guard/hooks/test_session_delegation_recovery.py
```

Automated tests prove contracts, not host delivery. Release acceptance additionally requires one-Mac real-host
evidence for both directions and repeated idle wake, with no open blocking P1/P2 defect.

## Requirement mapping

```text
plugins/spec-guard/hooks/native_collaboration_runtime.py       -> pinned private runtime
plugins/spec-guard/hooks/native_collaboration_adapters.py      -> explicit host attachment/removal
plugins/spec-guard/hooks/native_collaboration_retire.py        -> safe identity retirement
plugins/spec-guard/hooks/session_routing.py                     -> one-route selection and outcome validation
plugins/spec-guard/hooks/session_delegation_*.py                -> bounded host creation and result delivery
plugins/spec-guard/skills/collab/SKILL.md                       -> daily natural-language mailbox use
plugins/spec-guard/skills/session-routing/SKILL.md              -> existing-session routing
plugins/spec-guard/skills/session-delegation/SKILL.md           -> bounded new-session workflow
plugins/spec-guard/references/collaboration-runtime.md          -> operator reference
```
