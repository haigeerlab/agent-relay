# Task list: native Desktop wake and single-mailbox cutover

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Module: [`../../spec/collaboration-messaging.md`](../../spec/collaboration-messaging.md)

Tasks 1–2's host-feasibility evidence is complete. Task 3's Spec staging note and Task 4's
explicit pinned installer now exist in source. The runtime and narrow Task 5 host entries were
installed on one Mac for the
[ordinary-host acceptance](native-wake-ordinary-host-acceptance-2026-09-25.md): two-way messages
and one idle Codex wake passed without changing Chrome settings. Task 6 now has a
marker-gated one-step skill path. A
[controlled cutover trial](native-wake-controlled-cutover-2026-09-26.md) verified the fresh Codex
entry, then restored XATS because Claude Code account access failed before tool use. The complete
Claude ↔ Codex one-step journey and dual-Chrome acceptance remain pending. These checkboxes
do not authorize changes to user configuration, live services, messages, Git remotes, or app
permissions. XATS remains the supported default until the go/no-go checkpoint and subsequent
reviewed delivery.

## Task 1: Prove exact current-session binding primitives

**Description:** Find and verify host primitives that let an Agent bind its own Claude Code or
Codex Desktop conversation without asking the user for a task/session ID. Start with read-only
host evidence and an isolated mailbox; use two open Codex tasks to reject title/project guessing.
The [2026-09-25 identity preflight](native-wake-identity-preflight-2026-09-25.md) found a candidate
current-task environment variable on two same-project root tasks, each matching its own Desktop
task ID. The [Codex wake smoke](native-wake-codex-smoke-2026-09-25.md) proved a second task's
self-registration and a two-way idle-wake exchange. The
[cross-host smoke](native-wake-cross-host-smoke-2026-09-25.md) additionally proved Claude
self-registration and Claude ↔ Codex idle wakes. The
[failure and fork smoke](native-wake-failure-fork-smoke-2026-09-25.md)
proved Claude fork identity, offline retention/recovery and explicit hold, but found inaccurate
upstream hold and acknowledgement descriptions. The one-step entry and accurate user-facing
failure copy remain Task 6 delivery requirements, not prerequisites to prove these host primitives.
The [communication contract audit](native-wake-contract-audit-2026-09-25.md)
also found that this upstream revision treats agent names as same-user routing labels rather
than enforced per-session identities; the user chose that same-user cooperative boundary for
this capability. The ordinary one-step `collab` binding test belongs to Task 6 before cutover.
The [fresh Desktop trial](native-wake-desktop-idle-trial-2026-09-25.md) independently woke
this Codex task from idle after a Desktop restart, using the task's own environment ID internally;
it did not exercise the ordinary `collab` entry.

**Acceptance criteria:**
- [x] Each fresh Claude or Codex session can derive and bind its own live conversation without a
      user-supplied ID, without claiming per-session access control against same-user clients.
- [x] A message to one idle Codex task wakes that task, not another same-project task.
- [x] Busy, absent, and permission-held cases preserve unhandled mail and expose distinguishable
      status fields; Task 6 must replace inaccurate upstream explanatory copy.

**Verification:** Isolated real-host send → wake → inbox → acknowledgement record; the Agent may
pass its host-derived ID internally, but the user never supplies one. If exact Codex binding
fails, record no-go and stop replacement work.

**Dependencies:** None.

**Likely files:** this module's acceptance record only.

**Scope:** Small, investigation and evidence.

## Task 2: Prove a pinned communication-only upstream surface

**Description:** Audit one immutable upstream revision and verify that Spec Guard can expose only
mailbox/discovery/status tools on both hosts, without running upstream's broad `setup` or installing
its worker skills.
The [2026-09-25 tool-surface preflight](native-wake-surface-preflight-2026-09-25.md) found
unconditional worker-tool registration. The pinned upstream's 70 tests and dependency audit
passed. The [Codex wake smoke](native-wake-codex-smoke-2026-09-25.md) showed the Codex callable
catalog restricted to communication tools.
The [cross-host smoke](native-wake-cross-host-smoke-2026-09-25.md) also showed Claude's fresh
callable catalog restricted to the same ten communication tools.
The [fresh Desktop trial](native-wake-desktop-idle-trial-2026-09-25.md) separately exposed
only eight communication tools through the Codex `enabled_tools` allowlist. Its trial entry and
isolated data were removed after acceptance.
The [surface decision](native-wake-surface-decision-2026-09-25.md) treats a raw disallowed-tool
call as follow-up hardening, not a gate under the chosen same-user cooperative boundary; the
upstream server is not claimed to enforce per-session or per-process access control.

**Acceptance criteria:**
- [x] Both actual host tool catalogs exclude worker/review/orchestration tools.
- [x] A fixed revision, license, Node requirement, private storage and no-listener behavior are recorded.
- [x] Upstream tests and dependency audit pass outside any misleading sandbox-only permission failure.

**Verification:** Actual host tool-catalog snapshots plus documented host filtering;
pinned-revision build/check/audit in an isolated test directory. A raw blocked-tool call is
deferred because this same-user mailbox does not promise process-level isolation. Any authorized
temporary host entry must be removed and compared with its pretrial backup. If tool restriction
cannot be proved, record no-go.

**Dependencies:** None.

**Likely files:** this module's acceptance record only.

**Scope:** Small, investigation and evidence.

## Checkpoint: Go or no-go

- [x] Tasks 1–2 pass for same-user cooperative host feasibility; XATS remains the daily default.
- [x] This is not permission to cut over: Task 6 still must prove the one-invocation `collab`
      journey before replacing XATS.
- [ ] Review whether the private IPC and upstream maintenance risk remain acceptable.
- [ ] Obtain explicit review of any proposed change to the accepted module Spec.

## Task 3: Amend the collaboration contract

**Progress:** The accepted Spec now describes the optional experimental backend and explicitly
preserves XATS as the active transport. Final replacement clauses and operator references wait for
the one-step host adapter and cutover evidence.

**Description:** After a go decision, update the accepted module Spec and operator references to
describe one new backend, the experimental wake boundary, delivery states, and old-mail archive.
Keep `collab` language and message-as-information safety rules unchanged.

**Acceptance criteria:**
- [ ] Fixed-XATS, mailbox-only, and tmux-specific clauses are revised only where replacement requires it.
- [ ] No project topology, automatic task orchestration, or implicit host/service setup appears.
- [ ] The plan records the reviewed immutable upstream revision and cutover prerequisites.

**Verification:** Spec/Plan review and repository document validation.

**Dependencies:** Go/no-go checkpoint.

**Likely files:** `spec/collaboration-messaging.md`, `plugins/spec-guard/references/collaboration-runtime.md`.

**Scope:** Medium, documentation contract.

## Task 4: Package the private bridge runtime

**Progress:** `native_collaboration_runtime.py` pins commit
`8f12c880cfdba73812b6ab7bc0f373fc467e0343`, checks Node >=22.5, fetches that revision,
installs locked dependencies with install scripts disabled, builds without upstream `setup`, and
validates an owner-only runtime/mailbox. The host fragments also redirect the upstream XDG data
home into that private runtime: without it, the server tried writing its worker schema into an
existing `~/.local/share/claude-codex-bridge/runs` path at startup. An isolated temporary
real-host install returned `ready` and the server started with the redirected path;
an isolated MCP `tools/list` returned the expected 17 upstream tools (ten communication tools
and seven denied tools). The installer now creates a private `mailbox/backups/` directory and
status rejects unsafe backup directories/files. An explicit probe started the pinned build with
a disposable mailbox and observed all 17 tools; it never opened the real mailbox. A later
explicit installation and real-host startup passed; live backup creation and restoration still
need final acceptance.

**Description:** Add only the pinned open-source runtime needed for same-Mac messaging. Do not call
the upstream general installer, open a listener, or mutate existing XATS data.

**Acceptance criteria:**
- [ ] Initialization is explicit, reproducible and fails closed on unsafe file ownership/permissions.
- [ ] One owner-only SQLite mailbox and backups live outside project worktrees.
- [ ] Absent runtime and failed startup give an actionable diagnostic without changing user settings.

**Verification:** Focused runtime fixtures, pinned upstream checks, and no-secret/no-listener audit.

**Dependencies:** Task 3.

**Likely files:** `plugins/spec-guard/hooks/collaboration_runtime.py`, focused runtime tests.

**Scope:** Medium, one runtime slice.

## Task 5: Connect ordinary Claude and Codex hosts narrowly

**Progress:** Print-only fragments and explicit opt-in installers are implemented and tested on
temporary host files and then installed on one Mac for real-host acceptance. Codex appends only
its own table with ten communication tools. Claude checks
for an existing entry, writes seven exact deny rules before asking its CLI to add the user-scoped
server, and preserves unrelated settings such as Chrome; a failed CLI registration leaves the
deny rules in place. The real user host entries were added with private pre-install backups;
fresh-host catalogs and a two-way message smoke passed. Chrome control entry survived, but
full browser workflow acceptance remains open.

**Description:** Add explicit user-level host adapters for the private runtime while preserving
native Codex Desktop and both Chrome integrations. Do not switch to a managed app-server.

**Acceptance criteria:**
- [ ] Each host gets only communication tools; neither needs a second plugin.
- [ ] Generated configuration contains no secret and does not overwrite unknown existing entries.
- [ ] Fresh ordinary sessions connect after the documented restart, without changing Chrome settings.

**Verification:** Adapter tests plus fresh Claude Code and Codex Desktop tool-catalog checks.

**Dependencies:** Task 4.

**Likely files:** `plugins/spec-guard/hooks/collaboration_adapters.py`, adapter tests.

**Scope:** Medium, host adapter slice.

## Task 6: Preserve the one-step `collab` conversation

**Progress:** The same `collab` skill now selects exactly one backend using a read-only private
marker. With no marker, the current XATS journey is unchanged. A valid native marker enables
host-self-binding, inbox/discovery/send/ack guidance; invalid or unavailable native state stops
instead of splitting mail across backends. No code in this slice writes the marker, so the native
path still needs explicit cutover and ordinary-host acceptance before it can be called complete.
Source contract tests and a temporary-marker selector test cannot prove that a fresh host's
installed, one-invocation `collab` works: the ordinary skill reads the user-level marker, and
temporarily flipping that marker while XATS sessions may be active would split mail. This
acceptance is the first live check inside a separately approved, rollback-guarded cutover.

**Description:** Map registration, discovery, inbox, send, reply, acknowledgement, and wake-status
reporting onto the single new mailbox while keeping the existing natural-language entry.

**Acceptance criteria:**
- [ ] One `collab [optional alias]` joins without task IDs, project groups, raw tool names, or a second setup flow.
- [ ] Unique, absent and ambiguous peer names keep their current safe behavior.
- [ ] The sender sees mailbox, wake, read and acknowledgement as distinct outcomes; peer text grants no authority.

**Verification:** Focused entry contracts and same-/cross-project two-way mailbox tests.

**Dependencies:** Task 5.

**Likely files:** `plugins/spec-guard/skills/collab/SKILL.md`, `plugins/spec-guard/hooks/test_collab_entry.py`.

**Scope:** Medium, daily-use slice.

## Checkpoint: New backend works in isolation

- [ ] Tasks 4–6 pass without touching a live XATS mailbox.
- [ ] Both hosts can exchange and acknowledge messages after an idle wake.
- [ ] No extra user-visible plugin or worker tool is present.

## Task 7: Make cutover and rollback explicit

**Progress:** A read-only XATS SQLite preflight now counts registered non-proxy identities and
deliverable unread messages using the legacy recipient rule. Missing/unsafe/incompatible storage
fails closed; any registered identity requires separate live-session review. This is a snapshot,
not a switch. A matching native preflight uses the pinned bridge's schema v2 to count
unacknowledged direct and per-recipient broadcast deliveries before rollback. The
[controlled cutover design](native-wake-migration-plan.md#controlled-cutover-design--2026-09-25)
allows the user's requested read-only retention of old mail only after exact unread identities
and session liveness are reviewed. The controlled rollback left XATS at 8 registered and 3 unread;
native now has 0 registered and 0 unacknowledged. A private SQLite backup primitive and explicit operator
command now have fixture tests for WAL content, integrity, unread-state preservation,
non-overwrite, mandatory stopped-service assertion and reviewed inventory counts. The command
was also run against the real mailbox during the authorized trial, after separate confirmation
that XATS was stopped. Installed one-step cross-host verification and dual-Chrome acceptance remain open.
An operator-only activation command is now implemented and fixture-tested: it checks the private
archive checksum, integrity, reviewed counts and complete logical contents against the unchanged
source, then atomically
creates a non-overwriting selector marker. Its stopped-service and closed-session flags remain
human assertions; it was run on the real mailbox during the authorized trial.
An operator-only rollback command is fixture-tested as well. It requires an available XATS mailbox,
zero registered native identities and zero unacknowledged native deliveries before removing only
the selector marker; native mailbox history remains in place. Its stopped-native-sessions and
running-XATS flags are operator assertions, not process checks. The real trial exposed an
overstrict shared-parent permission check; a failing regression reproduced it, the scoped mailbox
check was corrected, and the guarded rollback then completed with XATS running and all history
retained. The trial did not complete the cross-host acceptance gate.
The [read-only legacy session audit](native-wake-legacy-session-audit-2026-09-25.md) found that
none of three stored Claude PIDs still runs, but the five Codex registrations lack an exact task
binding. It did not establish that all old sessions are closed or classify the three unread
deliveries as disposable.

**Description:** Design and test one operator-directed switch from XATS to the new mailbox. Check
old active sessions and unread mail first, retain the old private data read-only, and prevent one
session from accidentally using two daily inboxes. Do not auto-migrate historical messages.

**Acceptance criteria:**
- [ ] Cutover blocks on unresolved old sessions or unreviewed unread messages; any retained
      historical unread delivery remains in the private archive, never silently dropped.
- [ ] Old data is preserved; no cleanup/deletion or service shutdown happens without explicit approval.
- [ ] Rollback identifies new-backend unread mail and never silently strands it.
- [ ] The installed one-step skill and both Chrome workflows pass before live cutover.
- [ ] A consistent private XATS archive passes integrity, count and checksum checks before the
      marker is written; the 3 currently unread deliveries remain unread in retained history.

**Verification:** Cutover/rollback fixtures and one controlled real-host rehearsal with test data.

**Dependencies:** Task 6.

**Likely files:** operator skill/reference, runtime/adapter tests.

**Scope:** Medium, transition slice.

## Task 8: Complete real-host acceptance and delivery review

**Description:** Verify the ordinary user journey, including busy/idle/restarted sessions and both
Chrome integrations, then run repository checks and review only this feature's diff.

**Acceptance criteria:**
- [ ] Claude ↔ Codex replies work in same and different projects with no manual relay.
- [ ] ChatGPT in Chrome and Claude Code in Chrome both work after fresh host restart.
- [ ] Wake failure preserves unread mail; no message is described as read or handled without evidence.

**Verification:** Sanitized real-host acceptance; focused collaboration tests;
`/bin/bash scripts/validate.sh`; `/bin/bash evals/codex-plugin-smoke.sh --selftest`;
`git diff --check`.

**Dependencies:** Task 7.

**Likely files:** acceptance record and relevant tests/docs only.

**Scope:** Medium, acceptance slice.

## Checkpoint: Ready for review, not automatic release

- [ ] All tasks and focused/full checks pass; no unrelated changes are included.
- [ ] Old mailbox archive and explicit rollback instructions are readable to the operator.
- [ ] Native wake remains labelled experimental until supported host API or repeated compatibility evidence exists.
