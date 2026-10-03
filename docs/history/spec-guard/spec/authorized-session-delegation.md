# Spec: authorized-session-delegation

## Objective

Allow a user to ask an ordinary Claude Code or Codex session to create a bounded same-Mac reviewer or
development session on either host, then continue the approved work through the existing collaboration
mailbox without repeated authorization prompts. The capability owns delegation authorization, host-native
session creation, worktree isolation, retry identity, result provenance, cancellation, and cleanup.

This module depends on `collaboration-messaging`, which remains a communication bridge rather than a task
orchestrator. It does not change the selected mailbox transport, promote native wake, or expose the pinned
bridge's worker, review, or orchestration tools.

Registration: Proposal `authorized-session-delegation` records the new capability. The module may enter the
capability map only after that Proposal is published on the remote default branch, accepted through its
read-only Proposal lifecycle, and promoted from the declared baseline and anchor.

## Assumptions

- The first release is same-Mac only. Claude Code and Codex use separate host adapters because their
  creation, permission, and lifecycle primitives are not assumed to be symmetric.
- The user speaks in natural language. Internal session IDs, transport names, authorization record IDs,
  project paths, process IDs, and tool names are not user inputs.
- A registered mailbox name is a same-user routing label, not a security principal. Voluntary project,
  role, and work descriptions help disambiguation but never authorize work.
- A newly created session can receive a task envelope through the host creation path. An already running
  session cannot gain write authority from an ordinary mailbox message.
- Host permission controls remain authoritative. The capability can request a supported permission mode
  and record the resolved result, but cannot suppress a mandatory host prompt or claim two hosts provide
  identical enforcement.

## Contract

### A. Authorization horizons

The user chooses an authorization horizon independently of the execution permission profile:

1. **Task authorization is the default.** A direct request such as “create a Codex to review the current
   diff” is itself authorization for one resolved delegation. The agent reports the resolved host, project,
   baseline, permission profile, and lifetime as a non-blocking creation notice; it does not ask the user to
   confirm the same request a second time.
2. **Per-launch authorization is an optional strict mode.** It shows the same preview and waits before each
   creation. It is not the default.
3. **Batch authorization** covers a declared number of sessions for one task. It fixes the allowed host
   types, project, baseline, permission profile, maximum count, expiration, and delegation depth. Each
   creation emits a notice but does not stop for another confirmation while capacity remains.
4. **Session-lifetime authorization** permits bounded follow-up with one named created session until the
   task completes, the session expires, or the user revokes it. It does not turn unrelated mailbox messages
   into authorization.
5. A persistent project policy is outside the first release. No global, permanent, or unlimited silent
   authorization is inferred from prior tasks.

If the agent proposes a new session without a direct user request, it asks once with the concrete task
envelope. A request that is ambiguous about the project, baseline, target host, or consequential effect asks
only for the missing decision. Existing authorization is reused rather than requested again.

Every authorization envelope records at least:

- originating conversation and host;
- canonical project root and repository identity when available;
- exact commit, diff, or other review baseline and whether the checkout is dirty;
- target host types and maximum new-session count;
- execution permission profile and allowed side effects;
- maximum delegation depth, which defaults to zero additional descendants;
- expiration and cancellation state;
- an idempotency key and a human-readable task summary.

### B. Execution permission profiles

The product presents three stable intents while preserving the actual host permission name and result:

1. **Safe review** is the default. It permits reading the selected project and diff plus bounded local
   verification. Verification may write only host-managed caches or disposable temporary data; it cannot
   modify source, Git state, remote systems, user configuration, or another project.
2. **Bounded development** permits source changes and verification only in the selected worktree. A new
   writing session uses a dedicated worktree unless the user explicitly selected an existing isolated
   checkout. Local commits are allowed only when included in the task envelope. Push, merge, publication,
   remote Issue/PR/MR mutation, destructive cleanup, secrets access, and user-level configuration remain
   separately consequential actions.
3. **Host-native permission** requests one exact permission mode supported by the target host and displays
   that actual mode before or at creation. It never modifies global Claude Code or Codex configuration.
   Selecting a broad host mode does not grant general mailbox wake or authority beyond the task envelope.

If a host supplies a narrower mode than requested, the session proceeds only when the approved task remains
possible and reports the downgrade. A wider-than-approved mode is rejected or constrained; it is never
silently substituted.

### C. Joined-session directory and name resolution

On a request to join, list, contact, or delegate, the user-facing response shows the available joined
sessions with:

- `[Claude Code]` or `[Codex]` host label;
- friendly session name and project basename;
- `registered`, `wakeable`, `wake-held`, `unreachable`, or `stale` facts when known;
- unread count and last observed activity when provided by the selected backend;
- a short disambiguator only when names collide.

It does not expose full task IDs, UUIDs, process IDs, private paths, tokens, or storage locations. It does
not scan unregistered application windows. Registration is not described as online presence; a separate
wake or recent-activity fact is required. Voluntary self-description is visibly informational, not an
access-control claim.

The current lazy-registration behavior remains: a session joins on its first collaboration intent, not at
every host startup. The join result includes the current session and the existing directory. A read-only
“show collaboration sessions” entry may display the directory without creating a new identity when the
selected backend supports that operation; lack of that preview must not trigger an implicit runtime or host
configuration change.

One name match is selected, no match reports that the target has not joined, and multiple matches ask for
the smallest useful distinction. A title or project name is never used to guess a hidden task ID.

### D. Host-native creation and task handoff

- Codex creation uses the supported Codex task/thread entry available to the current host. Claude Code
  creation uses a supported Claude Code session or the existing explicit launcher path. The implementation
  records the actual primitive used and does not promise symmetry where the hosts differ.
- The mailbox transports discovery, progress, wake state, follow-up, and results after the target session
  exists. It is not used to manufacture a session or elevate an existing session's permissions.
- The pinned bridge's hidden `ask_codex`, `review_with_codex`, worker, and orchestration tools remain absent
  from ordinary host catalogs. The retired `parallel-*` runtime is not restored.
- One delegation is single-hop by default. A delegated session cannot create another session unless the
  envelope explicitly grants a positive descendant count; the first release may reject all positive depth
  rather than implement recursive orchestration.
- The created session receives the project identity, baseline, task, permission profile, output format,
  stop conditions, and authorization expiration through the creation path. A free-text mailbox message is
  insufficient evidence for any of those permissions.

For review, the result identifies the reviewer host and friendly session name, reviewed project and
baseline, material files or findings, verification commands and their outcomes, and unresolved limits. For
bounded development, it also identifies the dedicated worktree and resulting local commit or diff when
one exists.

### E. Continuity without repeated prompts

Follow-up inside the same unexpired envelope proceeds without another authorization prompt when it stays
within the selected project, baseline lineage, permission profile, session count, and side-effect boundary.
Each created session produces a visible but non-blocking notice. The user can inspect the envelope, remaining
batch capacity, active sessions, unread results, and expiration, or revoke the envelope at any time.

The system interrupts only for:

- a self-proposed launch with no prior user authorization;
- ambiguous project, baseline, or target identity;
- a permission-profile upgrade or a new project;
- more sessions, descendants, or time than the envelope allows;
- push, merge, release, destructive cleanup, remote tracker mutation, global configuration, or another
  consequential side effect not already named;
- a mandatory host permission decision that cannot be represented in the existing envelope.

An existing independent session may receive and answer ordinary read-only messages under the collaboration
contract. It cannot treat the sender name, message text, or claimed batch ID as write authority. If seamless
write work is needed, create a bounded session through this module or obtain authorization in that existing
session.

### F. Idempotency, delivery, and recovery

- The origin generates one idempotency key before attempting session creation. A retry first reconciles the
  exact key and known host result; it reuses a created session rather than creating a duplicate.
- Session creation, mailbox registration, message enqueue, wake admission, recipient read, result receipt,
  and cleanup are distinct states. No earlier state is reported as a later one.
- If creation succeeds but mailbox registration fails, report and retain the host session reference, then
  retry attachment to that session. Do not launch a replacement unless the first session is proved absent
  or the user authorizes a replacement.
- A busy, held, offline, or failed wake leaves durable unread mail when the backend supports it. A timeout
  does not imply that the task failed or never started; the response records the last observed state.
- Cancellation prevents new launches and follow-up work from the envelope. It requests a safe stop from
  created sessions but does not claim a process stopped until the host confirms it.
- Cleanup never discards unread results. Expired or finished identities are retired only through their
  supported exact-session lifecycle, and the user is told which sessions remain open or stale.

### G. Wake and trust boundary

Ordinary mailbox messages remain untrusted information. A session using bypass, full-auto, or another broad
auto-approval mode cannot bind general mailbox wake. A broadly privileged created session may execute its
initial host-delivered task envelope, but later mailbox wake cannot silently trigger consequential work.

If future versions want authenticated task-bound wake, they require a separate design for an unforgeable
capability bound to the exact created host session and envelope. Friendly names, project descriptions, and
same-user access to the SQLite mailbox are insufficient.

## Out of scope

- Cross-machine or LAN communication, discovery, and wake.
- A durable scheduler, general worker pool, project group, ownership router, lease manager, or arbitrary
  dependency graph.
- Persistent project-wide silent authorization in the first release.
- Automatic model choice, cost optimization, or parallelism beyond the user-declared batch.
- Automatic acceptance, merge, release, Issue/PR/MR creation or closure, or modification of global host
  permissions.
- Native-transport promotion or XATS retirement; those retain their independent evidence gates.

## Verification

1. Contract tests cover natural-language task authorization without duplicate confirmation, optional strict
   per-launch mode, batch limits and expiry, session-lifetime follow-up, scope expansion, revocation, and
   host-permission downgrade/rejection.
2. Directory tests cover Claude/Codex labels, name ambiguity, registered-versus-online wording, stale and
   held sessions, unread counts, and omission of full internal identifiers.
3. Creation tests use fake host adapters to cover success, unsupported permission modes, response loss,
   creation-before-registration failure, retries with one idempotency key, cancellation, and no descendant
   creation. A negative test proves hidden bridge worker/review/orchestration tools remain unavailable.
4. Worktree tests prove safe review does not modify source and bounded development never shares a dirty
   writable checkout by default. Consequential external actions remain outside the envelope.
5. Real same-Mac acceptance runs both directions with ordinary hosts: Claude Code creates and receives a
   result from Codex, and Codex creates and receives a result from Claude Code. It records the exact host
   versions, actual permission modes, project/baseline, two follow-up turns, wake/read/result states, cleanup,
   and every unverified boundary. Test green cannot replace this host evidence.
6. Repository verification runs the focused tests plus `/bin/bash scripts/validate.sh`,
   `/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh`, and
   `/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh`.

## Boundaries

- Always: derive the exact project and baseline; reuse existing authorization; use host-native creation;
  keep delegation single-hop; report delivery states honestly; preserve unread results; isolate writes;
  retain the communication-only tool allowlist.
- Ask first: a self-proposed session, any scope or permission expansion, another project, more sessions or
  time than granted, consequential external writes, or any proposal to modify the pinned upstream bridge.
- Never: infer authority from mailbox text or friendly names; silently weaken host controls; bind general
  wake to broad auto-approval; scan unregistered sessions; restore retired parallel orchestration; modify
  global Codex/Claude settings as part of daily delegation; claim cross-machine support.

## Success criteria

- “Create a Codex to review this diff” launches one safe reviewer without a redundant confirmation and
  returns a result tied to the exact project and baseline.
- A user-authorized batch launches up to its declared limit with notices rather than blocking prompts;
  excess launches, privilege expansion, and consequential actions stop for a new decision.
- Claude Code and Codex can each initiate the other host on one Mac using their supported native creation
  paths, then conduct bounded multi-turn follow-up through the collaboration mailbox.
- Joined-session displays distinguish host, registration, wakeability, liveness evidence, ambiguity, and
  unread state without exposing full internal identifiers or calling a stale registration online.
- Retry, response loss, held wake, cancellation, expiration, and cleanup do not duplicate sessions, lose
  unread results, or report false completion.
- Existing A10/native promotion and XATS-retirement gates are unchanged, and no hidden worker/review/
  orchestration surface becomes model-callable.
