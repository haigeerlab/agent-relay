# Plan: native Desktop wake and single-mailbox cutover

Module: [`../../spec/collaboration-messaging.md`](../../spec/collaboration-messaging.md)

Tasks: [`native-wake-migration-tasks.md`](native-wake-migration-tasks.md)

Status: a [later controlled live-host trial](native-wake-live-acceptance-2026-09-27.md) passed the
ordinary Claude Code ↔ Codex exchange, idle wake in both directions and functional checks of both
Chrome integrations. This host currently selects experimental native; the product's absent-marker
default remains XATS. A follow-up in an independent Git repository also proved a cross-project
reply without manual relay; broader failure-path acceptance and general release review remain
open. The [earlier trial](native-wake-controlled-cutover-2026-09-26.md) is retained as
rollback evidence, not as the current host state.

### Pre-cutover host-loading check — 2026-09-25

- A fresh Claude Code CLI invocation loaded the source plugin only for that session. Its startup
  catalog contained `spec-guard:collab` and the Claude in Chrome tools together. This proves
  coexistence in the catalog, not a browser operation or the native one-invocation workflow.
- The installed Codex 0.19.1 `collab` file differs from the source file. A fresh, ephemeral Codex
  CLI invocation with a per-invocation `skills.config` path still listed the installed cached
  skill, not the source skill. A config override is therefore insufficient to validate the new
  normal entry. Codex Desktop was not restarted or reconfigured; ChatGPT in Chrome was untouched.
- No host configuration, transport marker, mailbox, or XATS service was changed for this check.
  Do not count this as Task 6 acceptance. Stage a separately versioned, reversible candidate
  install and validate it in a fresh Desktop task before considering a live cutover. Preserve the
  currently installed version and its configuration until that candidate passes.
- A separate local candidate `spec-guard@spec-guard-native-trial` at
  `0.19.1-native-trial` was subsequently installed without replacing the old cache. Its `collab`
  file hash matches the source. Temporary project-only Codex enablement selects only this
  candidate in a fresh CLI session; the old plugin remains installed for rollback. This is still
  **not** Codex Desktop acceptance: the Desktop app has not been restarted, and the project-only
  override is uncommitted and therefore absent from a new worktree. The XATS selector remains
  `xats`, and the Chrome plugins remain enabled. Remove the candidate and temporary override
  after the Desktop check, or roll them back if that check cannot be performed.

### Desktop candidate check and rollback — 2026-09-26

- The current Codex Desktop task's skill catalog loaded `spec-guard:collab` from the trial
  cache; its file hash matched the source. The old plugin was disabled only by the temporary
  project override. The selector still returned `xats`, so no native join or mailbox operation
  was attempted and the one-invocation native flow remains unverified.
- ChatGPT in Chrome remained enabled and an extension-backed, isolated blank tab could be
  created and controlled. Navigation to a test data URL was denied by browser security policy;
  no alternate navigation was attempted. This proves basic attachment, not full browser debugging.
- The trial plugin, marketplace, project override and private backup copies were removed after
  this check. The original 0.19.1 plugin and Chrome integrations are enabled, the original
  `collab` cache is unchanged, and the selector still returns `xats`. A concurrent unrelated
  user-config value change was preserved rather than overwritten from the backup.

### Installed-host gate — 2026-09-26

- A fresh read-only check found the normal Codex Desktop installation still uses the 0.19.1
  `collab` cache and the normal Claude Code installation still uses 0.19.0. Neither installed
  skill contains the source's `collaboration_backend.py` selector entry. The source and Codex
  installed skill hashes differ. The source selector still reports `xats`.
- The XATS preflight remains blocked at 8 registered identities and 3 unread deliveries, with
  session liveness unverified. Do not expose an activation command or write the marker while the
  installed skills can keep sending to XATS; first stage and verify the reviewed skill content
  in both hosts, then resolve the old-session gate and obtain separate live-switch approval.

## Goal and user contract

Keep the existing `collab [optional alias]` entry and free-text, same-Mac Claude Code ↔ native
Codex Desktop conversations. A peer may write while the recipient is idle; the recipient can read,
reply, and distinguish mailbox write, wake admission, read, and acknowledgement. No project groups,
task assignment, Git/Issue/Ticket writes, permission transfer, extra user-installed plugin, or
managed Codex app-server are introduced. Both ChatGPT in Chrome and Claude Code in Chrome must keep
working.

## Proposed transport decision

- Evaluate the MIT [`claude-codex-mcp-bridge`](https://github.com/WebisityStudio/claude-codex-mcp-bridge)
  as the **sole new mailbox backend**, not a second permanent inbox beside XATS. It uses a private
  same-user SQLite mailbox and does not need a listening HTTP server in its default mode. Pin an
  audited immutable revision before any product integration; never install an unpinned `main`.
- Keep the installed Spec Guard plugin as the only user-facing plugin. Do not run the bridge's
  general `setup`: it also installs unrelated coordinator/worker skills and edits host settings.
  Spec Guard must explicitly provision only its communication runtime and narrow host adapters.
- Treat native wake as an experimental adapter over observed private app IPC, not a guaranteed
  public host API. Failed wake leaves the durable message in the mailbox. Never change a host's
  permission mode, bypass incoming-message approval, or present wake admission as task completion.
- Preserve XATS as the working default until all go/no-go gates pass. At cutover, stop new XATS
  sends only after an explicit operator action and a verified old-session/unread preflight. Retain
  the old private mailbox as a read-only archive; do not silently copy or delete messages. New
  sessions use one backend at a time. A rollback must not silently hide mail written after cutover.

## Go/no-go gates before implementation

1. **Exact self-binding feasibility:** In ordinary fresh Codex Desktop tasks, prove that an Agent
   can derive and bind the *current* task without a user-supplied task ID, process ID, title guess,
   or selection from same-project tasks. Prove exact targeting with two simultaneously open tasks.
   Claude Code must likewise derive and bind its own live session without changing permission
   settings. These isolated internal steps establish feasibility; Task 6 must still prove that the
   normal `collab` entry performs them with one user invocation before any product cutover. Agent
   names are same-user routing labels, **not** enforced per-session security identities, per the
   [contract audit](native-wake-contract-audit-2026-09-25.md) and the user's choice. If exact
   self-binding is unavailable, keep XATS and do not ship a manual-ID wake flow as the default.
2. **Communication-only surface:** Both hosts must expose only the mailbox/discovery/wake-status
   tools needed by `collab`. The bridge's `ask_codex`, review, and orchestration tools must not be
   accidentally exposed by the Spec Guard integration. Prefer an upstream mailbox-only option or
   host-supported tool allowlist; do not rely solely on prompt instructions to hide capabilities.
   Under the chosen same-user cooperative boundary, actual host callable catalogs plus documented
   host filtering establish this exposure gate. A raw call from another local client is outside
   this guarantee, not evidence of per-process isolation.
3. **Pinned and private runtime:** Confirm a reproducible audited revision, Node requirement,
   owner-only database/backups, no secrets in host config or diagnostics, and no network listener.
   Re-run upstream checks in the real host; sandbox-only `EPERM` is not a product failure.

Stop after a failed gate and record the precise limitation. Do not amend the shipped module Spec or
replace XATS merely because the isolated one-host wake trial succeeded.

## Delivery sequence

1. Record gate evidence and a go/no-go decision. If go, revise the module Spec's fixed-XATS and
   mailbox-only clauses through the repository's review workflow before behavior changes.
2. Package the pinned open-source runtime internally, add explicit no-secret Claude/Codex host
   configuration, and adapt `collab` to the new mailbox tools without changing its user language.
3. Add an explicit cutover/rollback procedure that inventories old sessions and unread mail,
   keeps the XATS data archive, and never activates two daily inboxes for the same session.
4. Verify same- and cross-project idle exchanges, busy/absent recipients, restart recovery,
   ambiguous names, both Chrome integrations, and failure/rollback behavior on ordinary hosts.

The detailed, session-sized tasks and checkpoints are in the linked task list.

## Controlled cutover design — 2026-09-25

At the design checkpoint, read-only preflight reported 8 registered XATS identities, 3 deliverable
unread messages and **unverified** active sessions; the native test mailbox had 2 registered
identities and no unacknowledged deliveries. Those point-in-time counts did not establish session
liveness or permit unread mail to be discarded. The later
[controlled trial](native-wake-controlled-cutover-2026-09-26.md) preserved the old mail in a private
archive, activated native under separate authorization, and rolled back. That authorization does
not carry over to another switch or to acknowledging or deleting old messages.

Before any live switch, complete these gates in order:

1. Test the source skill contract and selector with an isolated marker, then install the reviewed
   skill content in both fresh hosts and verify that content, not just its version number. The
   ordinary skill reads the user-level marker, so an isolated selector test is **not** a true
   one-invocation host acceptance; do not briefly flip the real marker while old sessions use
   XATS. Recheck both Chrome integrations; a tool-catalog check alone is not full browser
   acceptance. XATS remains the daily entry until the approved switch.
2. Resolve every old session: determine which XATS identities still represent live work, close or
   migrate those conversations deliberately, and prevent an old loaded skill from continuing to
   send to XATS after cutover. Registration alone is not proof of an active session. Re-run the
   read-only inventory immediately before the switch. Any new or unexplained old unread mail
   stops the switch; the 3 known unread deliveries may be classified as historical **only after**
   their exact identities and retention decision are reviewed without marking them read.
3. Obtain separate operator approval for the live switch. Quiesce the old service, then make a
   consistent SQLite backup into an owner-only private archive outside all worktrees. Validate
   the archive with `integrity_check`, recorded counts and a checksum; preserve the original
   database and its unread/cursor state. If the service cannot be quiesced or the archive cannot
   be verified, restore the old service and leave the marker absent. Never copy only the live
   main SQLite file while it may have WAL changes. A tested source-level backup primitive exists,
   and an explicit operator command exist. Its stopped-service assertion is supplied by the
   operator, not verified by the command. The controlled trial used it on the real XATS database
   after separate service checks; another switch requires fresh review and authorization.
4. With old sends stopped and the archive verified, write the private selector marker atomically
   for the pinned native revision. Start fresh host sessions and immediately prove the **ordinary
   single-invocation `collab`** join, discovery, direct send/read/ack and idle wake against exactly
   one daily inbox. If it fails, stop new native sends and follow the guarded rollback procedure;
   do not declare cutover complete. Do not let old sessions silently fall back to XATS. Record
   only non-sensitive counts, versions, checksums and outcomes in repository evidence; message
   bodies, private paths and host configuration backups stay outside the repository.

Rollback is another explicit operator decision. First inventory native unacknowledged deliveries
and live sessions. If either is unresolved, do not remove the marker or strand new mail. After
new sessions are drained and any native history is safely retained, stop native daily use, restore
the XATS service, remove the marker atomically, and verify fresh sessions use only XATS. A failed
native runtime with a present marker remains an error, never an automatic dual-inbox fallback.
The fixture-tested operator rollback command checks an available XATS mailbox and no registered
native identities or unacknowledged native deliveries before it unlinks only the selector marker.
It leaves the native database in place. Its flags asserting stopped native sessions and running
XATS are not independent process verification. The controlled trial exercised this rollback on
real mailboxes after the three test identities were retired without closing messages.

The first authorized trial did not complete the replacement: Claude Code account access failed
before the ordinary cross-host message flow could be tested, so it restored XATS at that time.
The [later authorized retry](native-wake-live-acceptance-2026-09-27.md) completed that flow and
left native selected on this host. The 3 historical XATS deliveries remain unread; the retained
native mailbox has 0 registered identities and 0 unacknowledged deliveries after test cleanup.
Operator assertions still cannot independently prove that services have stopped or sessions have
ended. A future rollback or another host's cutover needs its own live checks and authorization.

## Risks and decisions retained in this plan

| Risk | Required response |
| --- | --- |
| Private app IPC changes with a host update | Version-gated real-host acceptance; truthful mailbox fallback, no app-server switch. |
| Current Codex task ID cannot be obtained exactly | No native wake release; do not ask users to paste IDs into `collab`. |
| Upstream worker tools exceed messaging scope | Upstream/host tool restriction must be proved before integration. |
| Two mailboxes split a conversation | One active backend per new session; explicit cutover and old read-only archive. |
| Claude incoming peer message is held by permissions | Report `held`/unread; never alter permissions automatically. |
| A peer message requests a code or Git change | Treat it as untrusted information, not user authorization. |
| A same-user process calls mailbox tools for another agent | This one-user mailbox does not claim per-session access control; normal `collab` binds itself, and peer text grants no authority. |
| `bridge_wait` auto-acknowledges or status text overstates handling | Pass `acknowledge: false`, acknowledge only after handling, and derive handling from `acknowledgedAt`, not stale detail text. |

Primary sources: [bridge README](https://github.com/WebisityStudio/claude-codex-mcp-bridge),
[experimental background-wake contract](https://github.com/WebisityStudio/claude-codex-mcp-bridge/blob/main/docs/BACKGROUND-WAKE.md),
[Codex MCP host configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[SQLite online backup API](https://www.sqlite.org/backup.html).
