# Spec: host-native-session-routing

## Objective

Provide one user-facing, bidirectional session-communication surface that prefers each host's supported
native session channel for same-host conversations and keeps Spec Guard's durable collaboration mailbox
for Claude Code ↔ Codex conversations or an explicitly reported fallback.

The user identifies a session by host, friendly conversation name, and project description. Spec Guard
resolves the target, reports the chosen transport, and supports discovery, creation, send, reply, wait,
status, and cancellation without requiring internal IDs or repeated approval for an already authorized
task. The module is a thin routing and normalization layer; it does not reimplement Claude Code or Codex
session protocols.

Registration: inserted directly at the all-modules-complete checkpoint on 2026-10-04 after the user
reviewed and explicitly confirmed the exact `module-insert` preview. This module depends on
`collaboration-messaging` and `authorized-session-delegation`.

## Terminology and assumptions

- **Host-native Claude** means a supported Claude Code session directory and messaging operation exposed
  by the running Claude Code host, including its own reply/wake lifecycle. Spec Guard does not open or
  emulate Claude's private session socket.
- **Host-native Codex** means supported Codex App task/thread operations or the supported local app-server
  operations already used by the Codex adapter. Spec Guard does not infer a task from a window title or
  write directly to Codex's private state.
- **Spec Guard bridge** means the currently selected `collaboration-messaging` backend. Its internal
  selector may still be `xats` or `native`; this term must not be confused with host-native Claude or
  host-native Codex.
- The first release is one Mac only. Sessions may use different projects and worktrees on that Mac.
- All directions are bidirectional. Arrows in documentation describe a selected route, not a one-way
  capability.
- A friendly name, project description, bridge registration, or same-user process is a routing hint, not
  an authorization principal.

## Contract

### R1. One public control surface

The daily entry accepts natural-language requests equivalent to these operations:

1. `discover`: show sessions visible through supported host-native directories and sessions that have
   explicitly joined the Spec Guard bridge.
2. `create`: create a bounded Claude Code or Codex session through `authorized-session-delegation`.
3. `send`: send one message or task-scoped follow-up to an existing resolved session.
4. `reply`: answer through the exact route and conversation reference carried by the received message.
5. `wait`: wait through a supported host operation without acknowledging or inventing completion.
6. `status`: report the latest independently observed routing, delivery, wake, and response facts.
7. `cancel`: cancel only a created, authorized session through its exact host lifecycle.

Existing `collab` and `session-delegation` natural-language entries may remain separate skills, but they
must delegate to the same routing policy and return the same public fields. The user is never asked for a
thread ID, task ID, session ID, transport name, process ID, socket path, mailbox UUID, or database path.

### R2. Deterministic transport selection

For each message, reply, wait, or communication-status operation, the router selects exactly one primary
transport:

| Origin | Target | Primary transport |
|---|---|---|
| Claude Code | Claude Code | `host-native-claude` |
| Codex | Codex | `host-native-codex` |
| Claude Code | Codex | `spec-guard-bridge` |
| Codex | Claude Code | `spec-guard-bridge` |

Selection is based on the trusted current host and a uniquely resolved target host. A caller-provided
label cannot force a different adapter. A same-host native operation is attempted only when that host
exposes the required supported capability in the current session.

`create` and `cancel` remain host lifecycle operations owned by `authorized-session-delegation`; they report
their actual `hostOperation` separately. The matrix describes the message/result route associated with the
session and never implies that a mailbox manufactures or terminates a host session.

The result always includes `transport`. When the primary route cannot be used, the result also includes a
stable `routeReason`; it never silently changes transports. No message is sent twice merely because a
receipt or reply timed out.

### R3. Same-host native fast paths

- Claude Code ↔ Claude Code uses the host's own supported list, send, reply, and receipt/wake operations.
  Spec Guard may normalize their results but must not persist a second copy of the full message body in
  the collaboration mailbox.
- Codex ↔ Codex uses Codex task/thread operations exposed to the current App or the supported local
  app-server path. An existing task is contacted only through an exact host-returned task reference.
  Spec Guard must not guess from a title, project path, recent activity, or process inventory.
- Native session creation and cancellation remain owned by `authorized-session-delegation`. Routing does
  not create an unbounded worker pool or turn every new host window into a registered Spec Guard session.
- A native response uses the host-returned conversation/thread relationship. It is not copied into the
  bridge solely to make the transports look uniform.

Host-native capability absence is an ordinary, reportable condition. Unsupported Claude or Codex host
versions, CLI-only contexts without the required task tools, stale native references, and mandatory host
permission prompts must not be presented as communication failure on the other transport.

### R4. Cross-host durable bridge

Claude Code ↔ Codex messages continue to use `collaboration-messaging` so an offline, busy, or held target
can retain unread mail. The selected bridge backend remains single-valued and fail-closed: an invalid or
unavailable selector does not activate the other mailbox.

The bridge continues to separate message enqueue, wake admission, read/acknowledgement, reply, and task
completion. Existing communication-tool allowlists remain exact. Hidden worker, review, broadcast,
orchestration, lifecycle, and retired tracker-bridge tools are not exposed by this module.

### R5. Fallback without repeated interruption

If a same-host native capability is unavailable, Spec Guard may use `spec-guard-bridge` only when all of
the following are true:

1. the user's current task, batch, or session authorization already permits contacting that resolved
   target;
2. both endpoints are already and uniquely joined to the selected bridge;
3. the bridge is already enabled and ready; and
4. the response visibly reports `transport=spec-guard-bridge`, `fallbackFrom`, and `routeReason`.

This existing-ready fallback does not require a second confirmation for each message because it does not
expand the target, task, permission, project, session count, or side effects. Initializing a runtime,
starting a service, changing host configuration, registering another session, selecting a different
backend, or widening permission still requires the existing explicit authorization. If the four
conditions are not met, the operation stops with one actionable next step; it does not write to both
paths or ask repeatedly for the same unchanged decision.

### R6. Lazy participation and directory display

Opening a Claude Code or Codex conversation does not automatically create a Spec Guard bridge identity.
Host-native sessions are discovered on demand through the current host's supported directory. Bridge
participation remains lazy and occurs only on a collaboration intent or an authorized creation flow that
requires cross-host result delivery.

The joined-session display distinguishes the source and host:

~~~text
[Claude Code] reviewer · project-a · native-visible · idle
[Codex] api-check · project-b · bridge-joined · wake-held · unread 1
~~~

Each entry may show only facts its source actually supplies: host label, friendly name, project basename,
`native-visible` or `bridge-joined`, liveness/wake fact, unread count, and last activity. Unknown facts are
shown as unknown or omitted. Registration is not called online presence. Full internal identifiers,
private paths, PIDs, tokens, socket locations, and storage locations are never displayed.

One match is selected. No match explains which host or bridge join is missing. Multiple matches return the
smallest useful disambiguation using host, project basename, and a short opaque suffix supplied by the
controlling adapter. The router never scans unregistered windows or guesses a hidden identifier.

### R7. Normalized outcome without false equivalence

Every mutating or waiting operation returns these public facts when known:

- `transport`: `host-native-claude`, `host-native-codex`, or `spec-guard-bridge`;
- `target`: host label, friendly name, and project basename;
- `dispatch`: `accepted`, `enqueued`, `held`, `rejected`, or `unknown`;
- `wake`: `admitted`, `held`, `unavailable`, `not-applicable`, or `unknown`;
- `receipt`: `delivered`, `read`, `acknowledged`, `unavailable`, or `unknown`;
- `response`: `pending`, `received`, `cancelled`, `failed`, or `unknown`;
- optional `routeReason`, `fallbackFrom`, and one actionable `nextStep`.

An adapter reports only states that its host proves. It does not manufacture `read` from delivery,
`acknowledged` from wake, `received` from process exit, or `failed` from timeout. Host-specific diagnostic
states may be retained internally, but the public normalizer must preserve uncertainty rather than map a
stronger result.

Spec Guard stores only the minimum route metadata needed for idempotency, reply correlation, authorization,
and recovery. Same-host native message bodies are not copied into the bridge or a new transcript database.

### R8. Authorization and trust boundary

The authorization horizons and permission profiles from `authorized-session-delegation` remain
authoritative. A direct user request to contact a named session authorizes that bounded communication and
does not require a duplicate prompt. A self-proposed reviewer or developer session asks once with its
concrete task envelope. Valid task, batch, or session authorization is then reused until it expires,
completes, or is revoked.

Native delivery, a bridge message, or a reply never grants authority to modify code, Git, Issues/MRs/PRs,
services, host settings, or another project. The receiving session applies its own host permission rules.
The router cannot bypass a mandatory host prompt, alter global Claude Code or Codex configuration, add a
model override, or convert a communication authorization into a development authorization.

### R9. Idempotency, busy targets, and recovery

- Each logical send has one idempotency key before dispatch. Retries reconcile the same host result or
  bridge row and do not create a duplicate message, thread, or session.
- A busy target returns `held` or the nearest weaker proven state. The message remains durable only when
  the selected transport proves persistence.
- A timeout records the last observed facts and remains retryable. It does not trigger a replacement
  session or fallback after the primary route may already have accepted the message.
- Reply correlation is bound to the exact native conversation reference or bridge thread/subject. A
  friendly name alone is insufficient for a reply.
- Cancellation first freezes further authorized turns, then invokes the exact created session's native
  cancellation path. Ordinary messages to an independently existing session are not retrospectively
  cancellable.

## Out of scope

- Cross-machine, LAN, public-network, or Tailscale discovery, wake, and messaging.
- Reimplementing, reverse-engineering, proxying, or promising stability for a host's private transport.
- Automatically registering every new Claude Code or Codex conversation with the bridge.
- A permanent project-wide allow policy, unrestricted silent authorization, or automatic model choice.
- Automatic merge, push, release, Issue/PR/MR mutation, destructive cleanup, or global host configuration.
- Promoting the existing experimental `native` mailbox backend or removing XATS. A10's evidence gates remain
  governed by `docs/decisions/2026-09-28-xats-sunset.md` and its accepted 2026-10-04 single-Mac amendment;
  this module does not change them.
- Restoring the retired tracker bridge or the pinned bridge's hidden worker/orchestration surface.

## Verification

### Contract and unit tests

1. Route-matrix tests cover all four origin/target pairs, capability absence, exact target resolution,
   stable `routeReason`, and no silent or double dispatch.
2. Claude adapter tests prove same-host send/reply/wait use only supported Claude host operations and never
   write the body to the bridge. Unsupported capability and permission denial retain honest states.
3. Codex adapter tests prove same-host send/reply/wait use exact App task/thread references, never infer by
   title, and never duplicate a task after response loss.
4. Bridge tests prove both cross-host directions, durable unread delivery, held/offline wake, reply
   correlation, and continued exact communication-tool allowlists.
5. Fallback tests cover already-joined automatic fallback with visible reason, missing/ambiguous endpoint,
   unavailable bridge, runtime/config changes still requiring authorization, and a late primary receipt
   that must not cause duplicate fallback delivery.
6. Directory tests cover mixed native-visible and bridge-joined entries, same names across hosts/projects,
   stale registrations, unknown liveness, and omission of full internal identifiers.
7. Authorization and cancellation tests cover direct task flow without duplicate prompts, bounded batch
   reuse, expiry/revocation, scope expansion, permission negative cases, exact cancellation, and the rule
   that received text grants no authority.

### Real same-Mac acceptance

Acceptance uses ordinary installed hosts and records their exact versions and supported primitives. Each
successful path performs two turns in both directions and distinguishes send, wake, read/receipt, reply,
and completion evidence:

| Path | Required host evidence |
|---|---|
| Claude Code ↔ Claude Code | native discovery, A→B message and reply, B→A message and reply, busy/held case |
| Codex ↔ Codex | exact task discovery, A→B message and reply, B→A message and reply, wait/resume or unavailable fact |
| Claude Code ↔ Codex | bridge delivery and reply in both directions, durable unread behavior, wake unavailable/held case |

One controlled fallback acceptance disables or withholds a same-host native capability while both exact
endpoints are already bridge-joined, then proves the visible fallback reason and absence of duplicate
native/mailbox bodies. A permission-negative case and an exact-session cancel case are also required.

Test green does not replace host evidence. An unavailable host primitive is recorded as
`environment-unavailable`; it is not converted into a pass or a product failure.

Repository verification runs focused tests plus:

~~~bash
/bin/bash scripts/validate.sh
/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh
/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh
~~~

## Boundaries

- Always: prefer the supported same-host native path; use the bridge for cross-host communication; expose
  the selected transport and independently proven states; reuse bounded authorization; preserve exact
  identity, idempotency, and reply correlation; keep native bodies out of duplicate mailbox storage.
- Ask first: initialize/start a bridge runtime, modify host or project configuration, register another
  endpoint when no current authorization covers it, expand project/permission/count/time, create a
  self-proposed session, or perform any consequential external action.
- Never: silently change transport; dispatch the same logical message on two transports; infer task IDs or
  authority from titles/names/messages; scan real unregistered sessions; modify global host settings; add
  a Codex model workaround; claim cross-machine support; advance A10 or retire XATS from this module.

## Success criteria

- “联系这个项目里名为 X 的 Claude Code/Codex 会话” resolves one target and performs the operation with
  a visible transport and no internal-ID questions.
- Claude↔Claude and Codex↔Codex reuse their supported native communication capabilities; Claude↔Codex uses
  the durable Spec Guard bridge. All paths support a reply and are described as bidirectional.
- Existing task, batch, or session authorization keeps multi-turn work flowing without repeated prompts;
  meaningful scope or configuration changes still stop for one explicit decision.
- The session list distinguishes Claude Code/Codex and native-visible/bridge-joined entries, handles same
  names safely, and never equates registration with online presence.
- Busy, offline, permission-denied, timeout, response-loss, fallback, and cancellation paths preserve
  honest evidence and do not duplicate messages or sessions.
- A10's two-version/single-Mac/upstream-revision/no-open-P1-P2 promotion gate remains externally governed,
  XATS remains available, and this module introduces no cross-machine claim.

## Open questions

None for planning. If an installed host version does not expose a required supported same-host operation,
the implementation records that route as unavailable and exercises the bounded bridge fallback contract;
it does not fill the gap with private IPC.
