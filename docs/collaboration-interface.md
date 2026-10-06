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

## 6. Delivery semantics

| Item | Current (baseline) | Hardening target |
|---|---|---|
| Exactly-once | Not promised. The mailbox and a host inbox share no transaction; a host "accepted" ping is not "processed by the peer". S:plugins/spec-guard/references/collaboration-runtime.md:80-82 | Stated in the agent-relay README and tool descriptions — `delivery-state-machine` |
| Unknown is never replayed | Wake jobs: yes, B:src/wake-queue.ts:112-114. Routing: `nativeDispatch=unknown` only reconciles, never re-sends or falls back, S:plugins/spec-guard/skills/session-routing/SKILL.md:36-39, 61-62, 114-116 | Same rule for message delivery (gap b) — `delivery-state-machine` |
| Persist before submit | Present: message row before wake, job `sending` before the host call [BL §Gap analysis, item d] | Unchanged; covered by crash-injection tests — `durable-ordering` |
| Ordering, independence, cap | Partial [BL §Gap analysis, item e] | Per-recipient order, one recipient never blocks another, configurable pending cap with a proposed default — `durable-ordering` |
| Retry key and reply de-duplication | Partial: a reused key with different content returns the old message silently [BL §Gap analysis, item f] | Same key with different content is rejected; same original + same reply text is de-duplicated — `idempotency` |
| Evidence words | `delivered`, wake, ack, and reply are separate facts; fields without proof are `unknown`/`unavailable`, never inferred from exit status or activity. S:plugins/spec-guard/skills/session-routing/SKILL.md:75-79 | Unchanged |

## 7. Identity rules

| Item | Current (baseline) | Hardening target |
|---|---|---|
| Naming | Readable prefix (user alias or host + project) plus a short random suffix; lazily registered on first join/send/read intent. S:plugins/spec-guard/skills/collab/SKILL.md:24-30 | Unchanged |
| Reuse and takeover | A session reuses its first successful identity; it must not register, bind wake for, or take over another session's name. S:plugins/spec-guard/skills/collab/SKILL.md:32-34 — enforced by instruction only; `bridge_register` itself accepts any name, B:src/server.ts:104-158 | Server refuses re-binding a name to a different host session without explicit confirmation — `identity-check` |
| Sender | `from` is free text; an unregistered sender gets a warning only [BL §Gap analysis, item g] | `from` must match the calling host's identity; mismatch rejected — `identity-check` |
| Who may reply | Anyone may send on any thread [BL §Gap analysis, item g] | Only the addressed recipient may reply to a message id — `identity-check` |
| Missing identity | Wake binding stops when the session id cannot be confirmed; titles, processes, and recent activity are never guessed. S:plugins/spec-guard/skills/collab/SKILL.md:32-34 | Explicit guidance text returned to the agent — `identity-check` |

## 8. Authorization and wake rules

| Item | Current (baseline) | Hardening target |
|---|---|---|
| Default | Registration sets `wake: null`; binding only on the user's explicit request in the current session. S:plugins/spec-guard/references/collaboration-runtime.md:76-79 | Unchanged |
| Auto-approved sessions | Full-auto or bypass sessions must not bind wake (rule in skill and docs). Codex `approvals_reviewer = "guardian_subagent"` is **not** detected; two threads bound under it [BL §Findings 1] | Binding refused when the host session is auto-approved, guardian included — `identity-check` |
| Confirmations | Runtime install, host attachment, uninstall, identity retirement, and new wake bindings each need separate explicit approval. S:plugins/spec-guard/references/collaboration-runtime.md:29-94 | Unchanged |
| Permission files | Never written automatically; missing allow rules are diagnosed with a minimal suggestion. S:plugins/spec-guard/references/collaboration-runtime.md:96-102 | Unchanged |
| Messages are data | Mailbox text never authorizes code, Git, ticket, configuration changes, or new sessions. S:plugins/spec-guard/skills/collab/SKILL.md:18-20 | Unchanged |
| Codex manual approval | Under 请求批准 every mailbox tool call and controller run in a woken turn waits for a human; the App's "reduce prompts" dialog defaults Enter to 帮我批准 [BL §Findings 7] | Documented operating mode — unchanged |

## 9. Routing

| Item | Current (baseline) | Hardening target |
|---|---|---|
| Selector | `session_routing.py select` returns one `action` (`dispatch`, `observe`, `reconcile`, `stop`) and one `transport`, from facts `originHost`, `targetHost`, `authorizationState`, `targetResolution`, `nativeCapability`, `nativeDispatch`, `bridgeState`, `originJoined`, `targetJoined`; no message body in route JSON, argv, or logs. S:plugins/spec-guard/skills/session-routing/SKILL.md:20-34 | Unchanged |
| Claude ↔ Claude | `host-native-claude`: `ListAgents` + one `SendMessage`; nothing copied into the mailbox. S:plugins/spec-guard/skills/session-routing/SKILL.md:51-62; passed [BL §Results items 2-3] | Unchanged |
| Codex ↔ Codex | `host-native-codex`: App thread tools (`list_threads`, `send_message_to_thread`, `wait_threads`); a turn-based exchange, authorized per sending task. S:plugins/spec-guard/skills/session-routing/SKILL.md:88-118; transport passed [BL §Results item 4] | Unchanged |
| Claude ↔ Codex | `spec-guard-bridge` (the mailbox) is the primary transport. S:plugins/spec-guard/skills/session-routing/SKILL.md:122-123; passed both ways with wake [BL §Results items 5-6] | Transport label renamed with D1 (section 13) |
| Fallback | Only when the selector returns `spec-guard-bridge` with authorization, a ready bridge, and both sides uniquely joined; once; never after an unknown native dispatch. S:plugins/spec-guard/skills/session-routing/SKILL.md:36-39 | Unchanged |

## 10. Delegation

| Item | Current (baseline) | Hardening target |
|---|---|---|
| Permission intents | `safe-review`, `bounded-development`, `host-native`. S:plugins/spec-guard/hooks/session_delegation.py:27 | Unchanged |
| Authority and horizon | Authority `direct-user`, `confirmed-user`, `agent-proposed`, `mailbox` (the last two cannot create); horizon `task`, `strict`, `batch`, `session`. S:plugins/spec-guard/hooks/session_delegation.py:25-28 | Unchanged |
| Lifecycle | `create`, `continue`, `status`, `cancel` by friendly name with a short disambiguator; Claude uses background sessions, Codex the app-managed app-server. S:plugins/spec-guard/skills/session-delegation/SKILL.md | Unchanged |
| Public JSON | `state`, `hostOperation`, `hostStatus`, `transport`, `dispatch`, `wake`, `receipt`, `response`, `resultDelivery` (`enqueued`, `pending`, `missing`, `unverified`, `recipient-unavailable`), `routeReason`, `prerequisite`, `disambiguator` [BL §Results items 7-9] | Unchanged |
| Result return | Target sends the result to the origin's single wake-bound identity; origin is woken and acks. Passed both directions [BL §Results items 7, 9] | Unchanged |
| Expiry argument | `--expires-at` takes integer epoch seconds; ISO strings exit 2; undocumented [BL §Findings 2] | Accepts and documents one format — `ops-commands` |
| Held create | A create held on a prerequisite still persists a named envelope, which later makes the name ambiguous and cancels as `unknown` [BL §Findings 3] | A held create leaves no launchable envelope, or one that cancels cleanly — owner decided in the agent-relay capability map (translation keeps current behavior) |
| Claude round two | `continue` to an idle Claude target returned `held`/`target-busy` while `hostStatus=idle`, twice [BL §Findings 4]; passed on 2026-10-04 | Root cause found and fixed — owner decided in the agent-relay capability map |
| Background prompts | A Claude background session in `default` mode hangs on any permission prompt; `dontAsk` avoids it [BL §Findings 6] | Controller launches only in a mode that cannot hang — `ops-commands` reports it |
| Prerequisites | `held/project-allow-rules`, `held/project-trust`, `held/mcp-project-approval`, `held/host-permission-prompt`; read-only `permissions` preflight with `writesPerformed=false` [BL §Results items 8-9] | Unchanged |
