# Collaboration interface

The public contract of the collaboration capability that moves from Spec Guard into the standalone
`agent-relay` plugin. Defined by [spec/collaboration-interface.md](../spec/collaboration-interface.md) under
the accepted [collaboration-split Proposal](../spec/proposals/collaboration-split.md).

How to read it:

- **Current (baseline)** is what ships today. Every fact cites its evidence: `[BL §…]` is a section of the
  [pre-split baseline](baselines/collaboration-pre-split.md); `S:path:line` is Spec Guard at `54d0426`;
  `B:path:line` is the pinned upstream bridge `WebisityStudio/claude-codex-mcp-bridge@8f12c880` (MIT).
- **Hardening target** is where agent-relay must end up. Targets carry no final parameter values; each
  names its owning hardening module, where the values are decided.
- The agent-relay translation must reproduce the current column, apart from the two naming changes
  approved as D1 (section 13). The hardening modules must reach the target column.

## 1. Scope and versioning

- **What it is.** A private same-Mac channel between Claude Code and Codex sessions: a durable mailbox,
  best-effort wake of bound sessions, host-native routing for same-host pairs, and bounded cross-host session
  delegation. Messages are data, never authority.
- **What it is not.** Not a network service, not a tracker or job queue, not a cross-machine or
  cross-platform transport, not an authorization channel, not a general orchestrator. Upstream worker and
  orchestration tools stay disabled.
- **Interface version.** This document defines interface `1.0`. A change that removes or renames a tool,
  field, state, or command, or narrows an accepted input, is breaking and bumps the major number; additions
  bump the minor number.
- **Plugin version.** agent-relay follows its own semver, independent of Spec Guard. Its release notes state
  the interface version it implements.
- **Spec Guard requirement.** Spec Guard requires interface `>= 1.0, < 2.0` and checks it at run time
  (section 11); no host manifest dependency is relied on, because Codex 0.160 has none [BL §Prerequisites].

## 2. Tool list

### 2.1 MCP mailbox tools

The MCP server exposes exactly these ten tools to hosts. Current server name `spec-guard-native-collaboration`
(Claude) / `spec_guard_native_collaboration` (Codex), S:plugins/spec-guard/hooks/native_collaboration_adapters.py:23-24.

| Item | Current (baseline) | Hardening target |
|---|---|---|
| `bridge_register` | In: `agent` (unique readable name), `capabilities?` string[], `wake?` `"auto"` \| `{app: codex\|claude, sessionId}` \| `null` (omitted keeps the binding). Out: the agent row with wake binding. Registering again reactivates a retired agent. B:src/server.ts:104-158 | Reject a `wake` binding when the host session is auto-approved, including Codex `approvals_reviewer = "guardian_subagent"` (finding 1) — `identity-check` |
| `bridge_send` | In: `from`, `to` (name or `*`), `body`, `threadId?`, `idempotencyKey?`, `wake?` (default true), `allowUnregistered?`. Out: the stored message plus `warnings`. B:src/server.ts:159-200 | `from` verified against the host identity; body may come from a file path; returns a delivery state (section 5) — `identity-check`, `ops-commands`, `delivery-state-machine` |
| `bridge_inbox` | In: `agent`, `includeAcknowledged?`, `fromAgent?`, `threadId?`, `afterId?`, `limit?` (1–200, default 25), `maxChars?`, `maxBodyChars?`. Out: oldest-first page, `hasMore`. B:src/server.ts:226-248 | Expired messages hidden by default, readable on explicit request (D2) — `delivery-state-machine` |
| `bridge_ack` | In: `agent`, `ids` (≥1). Marks handled; history kept. B:src/server.ts:292-308 | Acknowledgement advances the matching wake job (finding 5) — `delivery-state-machine` |
| `bridge_outbox` | In: `agent`, `includeAcknowledged?`, `limit?` (1–200, default 30). Out: unacknowledged direct sends, newest first, with ping outcome and recipient status. B:src/server.ts:348-364 | Shows the delivery state of each send — `delivery-state-machine` |
| `bridge_agents` | In: `includeRetired?`. Out: agents with unread count, last activity, wake binding, recent ping health. B:src/server.ts:326-347 | Unchanged |
| `bridge_sessions` | In: none. Out: live Claude session ids and `thisSession` when the host exposes it; reads no content. B:src/server.ts:201-213 | Unchanged |
| `bridge_wake_status` | In: `agent?`. Out: up to 100 recent wake jobs with a per-state summary. B:src/server.ts:214-225 | Status by message id — `ops-commands` |
| `bridge_thread` | In: `threadId`, `beforeId?`, `afterId?`, `limit?` (default 30), `maxChars?`, `maxBodyChars?`. B:src/server.ts:309-325 | Unchanged |
| `bridge_wait` | In: `agent`, `fromAgent?`, `threadId?`, `timeoutSeconds?` (1–290, default 285), `acknowledge?` (default true), `limit?`, `maxChars?`. Waits for a new inbox message; cannot wake an ended turn. B:src/server.ts:249-291 | Wait on a specific message id's outcome — `ops-commands` |

### 2.2 Upstream tools that stay disabled

| Item | Current (baseline) | Hardening target |
|---|---|---|
| `bridge_retire`, `ask_codex`, `review_with_codex`, `bridge_orchestrate_codex`, `bridge_continue_codex`, `bridge_orchestration_wait`, `bridge_orchestration_status` | Listed as denied, S:plugins/spec-guard/hooks/native_collaboration_runtime.py:149-152. Claude gets exact deny rules, Codex an `enabled_tools` allowlist of the ten mailbox tools, S:plugins/spec-guard/hooks/native_collaboration_adapters.py:38-63. The probe fails if upstream exposes any tool outside the two lists, S:plugins/spec-guard/hooks/native_collaboration_runtime.py:191-197 | Unchanged; when agent-relay maintains the bridge itself (Phase 0 decision) these tools are removed from the server rather than denied — `safe-uninstall` reviews the host entries |

### 2.3 Command-line entries

| Item | Current (baseline) | Hardening target |
|---|---|---|
| Runtime | `native_collaboration_runtime.py status \| probe \| install [--root --node --npm]`; status never creates the runtime; install refuses an existing root. S:plugins/spec-guard/hooks/native_collaboration_runtime.py:200-214 | `doctor` aggregates status, probe, host entries and identity — `ops-commands` |
| Host adapters | `native_collaboration_adapters.py claude \| codex` (print fragments), `install-claude \| install-codex`, `uninstall-claude \| uninstall-codex --confirm-uninstall`. [references/collaboration-runtime.md, S:plugins/spec-guard/references/collaboration-runtime.md:41-69] | Back up host settings before any write; complete uninstall that keeps history — `safe-uninstall` |
| Identity retire | `native_collaboration_retire.py --name <exact> --confirm-retire`; refuses unacknowledged deliveries; keeps backlog. S:plugins/spec-guard/references/collaboration-runtime.md:84-94; 12 retirements [BL §Cleanup] | Unchanged |
| Delegation controller | `session_delegation_control.py [--state-root --native-root --node --claude-bin --codex-package-root] list \| permissions \| create \| continue \| status \| cancel`. `python3 -B …/session_delegation_control.py --help` | Unchanged (fixes in section 10 targets) |
| `whoami`, status/wait by message id, body from file | None (gaps h, i) [BL §Gap analysis, items h and i] | Provided — `ops-commands` |

## 3. Message structure

| Item | Current (baseline) | Hardening target |
|---|---|---|
| Stored message | `id` (integer, increasing), `from_agent`, `to_agent`, `body`, `thread_id?`, `idempotency_key?`, `created_at`. Unique `(from_agent, idempotency_key)`. B:src/schema.ts:27-40 | Adds a delivery state and its timestamps (section 5); idempotency key requires identical content (gap f) — `delivery-state-machine`, `idempotency` |
| Acknowledgement | `(message_id, agent)` primary key, `acked_at`, `note?`. B:src/schema.ts:42-47, 103 | Unchanged |
| Agent | `name`, `capabilities`, `registered_at`, `last_seen`, `retired_at?`, `retired_by?`, `retire_note?`; wake binding in `wake_targets(agent, target)`. B:src/schema.ts:49-54, 82-84, 100-102 | Records the host identity it was bound from — `identity-check` |
| Wake job | `message_id`, `agent`, `target`, `state`, `attempt_id`, `attempts`, `retry_at`, `created_at`, `detail`, `pending_reason?`, `notified_at?`; unique `(message_id, agent)`. B:src/schema.ts:85-94, 104-105 | Unchanged shape; state rules in section 5 |
| Reply | No reply-to field; a reply is an ordinary send on the same `threadId`. B:src/server.ts:159-200 | Replies carry the original message id; only its recipient may reply; same original + same text is de-duplicated (gaps f, g) — `idempotency`, `identity-check` |

## 4. Session states

*Registered is not online.* A registered row says only that a name exists.

| Item | Current (baseline) | Hardening target |
|---|---|---|
| registered | A non-retired row in `agents`; says nothing about liveness. [BL §Results item 1] | Unchanged |
| wake-bound | Row has a `wake_targets` entry (`claude` session id or `codex` thread id). [BL §Results item 1] | Binding refused for auto-approved sessions (finding 1) — `identity-check` |
| wake-held | Host accepted no ping because of permission, trust, or busy state; reported in `bridge_wake_status`. B:src/wake-queue.ts:9 | Unchanged |
| retired | `retired_at` set; hidden from `bridge_agents` unless requested; history kept. [BL §Cleanup] | Unchanged |
| live (Claude) | Seen in `bridge_sessions` / `ListAgents`; Claude background sessions can hang indefinitely on a permission prompt in `default` mode (finding 6). [BL §Findings 6] | `doctor` reports a session that is live but blocked — `ops-commands` |
| live (Codex) | A Codex App thread; under manual approval a woken turn waits for a human at every mailbox call (finding 7). [BL §Findings 7] | Documented operating mode; no automatic approval — unchanged |

## 5. Delivery states

*Enqueued is not read is not done.*

| Item | Current (baseline) | Hardening target |
|---|---|---|
| Message enqueued | Row written by `bridge_send`; durable before any wake. B:src/bridge-store.ts:371-385 | State `queued` — `delivery-state-machine` |
| Message read | Not recorded on the message; a wake job moves to `read` when the recipient fetches it. B:src/wake-queue.ts:105-109 | Explicit state on the message — `delivery-state-machine` |
| Message acknowledged | Acknowledgement row; shown as `acknowledgedAt` in outbox and wake status. [BL §Results item 6] | Unchanged |
| Message replied | Not tracked; inferred from a later message on the thread. | Reply linked to its original (section 3) — `idempotency` |
| Wake job states | `pending`, `sending`, `accepted`, `read`, `held`, `refused`, `unknown`, `cancelled`, `expired`. B:src/wake-queue.ts:9 | Unchanged as wake facts |
| Ambiguous submission | A job left `sending` past its retry time becomes `unknown` and is never replayed. B:src/wake-queue.ts:112-114 | Same rule for the message state machine (gap b) — `delivery-state-machine` |
| Expiry | Wake job `expired` after 1 h offline or 24 h busy; **the message stays readable and can still be acted on later** (gap c). B:src/wake-queue.ts:37-39, 119-124 | Message `expired` after a configurable queue timeout; hidden from inbox/wait by default, kept in history (D2) — `delivery-state-machine` |
| Wake after acknowledgement | Job stays `read` with detail "work is not yet acknowledged" after `acknowledgedAt` is set (finding 5). [BL §Findings 5] | Acknowledgement closes the job — `delivery-state-machine` |
| Target state machine | None as a message state (gap a). | `queued → sending → accepted \| failed \| unknown`, `queued → expired`; no transition out of `unknown` or `expired` except by explicit user action — `delivery-state-machine` |
