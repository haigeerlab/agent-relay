# Spec: codex-approval-presence

<!-- spec-guard: review approved b94323853d94 -->

## Objective

From a requirement relayed on 2026-10-19 by the Spec Guard monitoring session (mailbox name `spec-guard-monitor`, item
AR-1 of its round 21), answered "能做" with the user's consent (mailbox message #8004), the user asking for a reviewed spec
before any code, and the user's decision on the spec the same day ("14 条假设按草稿通过，6 个待决问题都按你的建议定"): when a Codex task stops at a host approval prompt, the decision inbox wants to tell the user to go and
click it in that task. It reads `bridge_agents` `presence`. Today a Claude session can be `waiting-approval` or
`waiting-input` (presence-and-approval D146, D148); a Codex task can only be `running`, `stopped`, `not-loaded` or
`unknown`. This module adds the two waiting values for Codex tasks the ChatGPT app has loaded.

Readers: the user; the round-2 coordinator (review, re-check after release); the Spec Guard owner and the decision inbox
(interface 2.6 is an addition within the accepted `>=1.0,<3.0`).

## What exists today (main 04143ce, v0.8.2)

- `bridge/src/presence.ts` `codexOwner` connects to `~/.codex/ipc/ipc.sock`, sends `thread-owner-discovery`
  (`{hostId: "local", conversationId}`, version 1) and maps the answer to `running` (an owner client is connected),
  `stopped` (no owner), `not-loaded` (connected, then silence; D200) or `unknown` (cannot connect). The owner's client id
  is in the answer's `handledByClientId` and is not kept.
- `bridge_agents` and `bridge_send`'s recipient check use `presenceOf` in `server.ts` with a 2 s cap
  (`AWAITING_PRESENCE_TIMEOUT_MS`, agents-view-polish D226); `bridge_outbox` `awaitingReply` uses
  `awaitingCodexPresence` with the same cap. `bridge_send` already warns about any recipient whose presence is
  `waiting-approval` ("waits until the user answers that prompt; nothing here can answer it", `addressing.ts`).
- `bridge/src/local-ipc.ts` `CodexIpc`: 4-byte little-endian length + JSON frames, at most 8 MiB per frame; it answers
  `client-discovery-request` with `canHandle: false`, resolves `response` frames by `requestId`, and drops every other
  frame ("Never publish unsolicited app broadcasts or conversation content"). It can send only `request` frames.
- `checkApprovals` (D148, every 30 s) notifies the user about Claude sessions only (`store.claudeWaiting()`).
- **Measured on the real host, read only, 2026-10-19** (owner session; test task in a test project, never in the user's
  working Codex projects): after discovery, a frame `{type: "broadcast", method: "thread-stream-following-changed",
  version: 1, targetClientIds: [owner], params: {conversationId, hostId: "local", following: true}}` makes the owner
  push `thread-stream-state-changed` broadcasts; the first has `params.change = {type: "snapshot", revision,
  conversationState}`, later ones carry patches. `conversationState.requests` is a list of pending server requests, each
  with a `method`; it was empty at the time. **The snapshot carries the whole conversation** (turns, items, command
  text). **No pending entry has been seen yet**: the user's Codex has `approvals_reviewer = guardian_subagent`, so the
  probe's commands were approved automatically.

## Assumptions (accepted by the user 2026-10-19)

1. **Signal source.** The ChatGPT app's own local IPC follower stream is the source; nothing else of Codex's is read
   (no private state files, no logs, no `~/.codex` database). If the app's protocol does not match (no owner, no snapshot,
   a snapshot without a `requests` list, an unknown `change.type`), the bridge reports what it reports today: `running`
   for a task with an owner. A wrong "waiting" is worse than a missed one.
2. **Classification by `method`**, entries with `completed: true` skipped:

   | `method` | presence | detail (fixed English, no request content) |
   |---|---|---|
   | `item/commandExecution/requestApproval` | `waiting-approval` | "waiting for your approval to run a command in its Codex task" |
   | `item/fileChange/requestApproval` | `waiting-approval` | "waiting for your approval to change files in its Codex task" |
   | `item/permissions/requestApproval` | `waiting-approval` | "waiting for your approval of a permission request in its Codex task" |
   | `item/tool/requestUserInput` | `waiting-input` | "waiting for your answer in its Codex task" |
   | `mcpServer/elicitation/request` | `waiting-input` (resolved question 1) | "waiting for your answer to a tool's question in its Codex task" |
   | any other method | ignored (stays `running`) | — |

   Several pending entries: `waiting-approval` wins over `waiting-input`. The permissions request counts as an approval
   because the user has to click allow or deny in the task, which is what the decision inbox reminds about.
3. **The entry shape is not confirmed yet** — the first task of the plan is to confirm it on the test task (see
   Requirements 1). What the spec relies on is only `method` and `completed`; whether an entry has its own timestamp is
   unknown. `since` is filled only if the entry carries a usable time; otherwise it is left out (it is optional today).
   If the confirmed shape contradicts this table, the spec comes back for review before any code.
4. **Read only, nothing kept, nothing forwarded.** The bridge reads `conversationState.requests[].method` and
   `.completed` (and a timestamp if assumption 3 finds one) and nothing else. The snapshot is parsed in memory and
   dropped; no part of the conversation (turns, items, command text, file paths, the request's own parameters) is
   stored, logged, put into `detail`, a notice or any tool result. This narrows the "never publish conversation content"
   rule of `local-ipc.ts`: broadcasts are still never published; only the follower snapshot for the thread the bridge
   asked about is read, and only those fields.
5. **The bridge never answers a request.** It sends only `thread-owner-discovery` and the two
   `thread-stream-following-changed` broadcasts (`following: true`, then `following: false`). It never sends
   `thread-follower-*` decision methods (for example `thread-follower-command-approval-decision`) or anything else that
   approves, denies, cancels, starts or steers a turn. A test pins the complete list of methods the presence code may send.
6. **Unfollow every time.** After the snapshot (or on timeout or error) the bridge sends `following: false` for the same
   thread and closes the socket. Closing the socket alone is not trusted to end the follow.
7. **Time cap.** The whole Codex lookup (connect, discovery, follow, snapshot, unfollow) stays within the existing 2 s
   cap (`AWAITING_PRESENCE_TIMEOUT_MS`); there is no second timer to tune. Discovery answered with an owner but no
   snapshot within the cap → `running`. Discovery silent → `not-loaded` as today (no follow is attempted). The same
   applies to `bridge_agents`, `bridge_send`'s recipient check and `bridge_outbox` `awaitingReply` (they share the
   lookup).
8. **Only loaded tasks are followed.** `stopped`, `not-loaded` and `unknown` are decided by discovery as today and are
   unchanged; a follow is sent only to the owner client named in `handledByClientId`.
9. **Frame size.** A snapshot larger than the existing 8 MiB frame limit makes `CodexIpc` drop the connection; the
   lookup then reports `running` (owner known). The limit is not raised: a long conversation simply loses the waiting
   detail (resolved question 3; task 1 records the test task's snapshot size).
10. **Interface only grows.** No new `presence.state` value: Codex now may also be `waiting-approval` or `waiting-input`,
    with `detail` (and `since` when known). `interface.json` 2.5 → 2.6; the `bridge_agents` row of
    `docs/collaboration-interface.md` says that since 2.6 a Codex task the ChatGPT app has loaded may also be
    `waiting-approval` or `waiting-input`, read from the app's own pending-request list, and that a Codex `running`
    means no pending request was seen, or the list could not be read within 2 s. Mailbox schema 7 unchanged.
11. **Out of scope** (resolved question 2): a desktop notice for a Codex task waiting for approval (`checkApprovals`
    stays Claude only — the decision inbox does the reminding for its user); approving anything; watching the stream
    continuously; reading Codex config (`approvals_reviewer` etc.).
12. **Release**: bridge change, version number decided by the user at release (resolved question 5), `upgrade --confirm`; interface 2.6.
13. **Test task**: the existing test Codex task in the dedicated test project; never
    create or touch a test task in the user's working Codex projects. To make a command stop at the user's prompt there,
    that test task needs approvals that ask the user rather than `guardian_subagent`; how to set that for one task
    without changing the user's global Codex config is part of task 1 and needs the user's go-ahead before any config
    change.
14. Module id `codex-approval-presence`; depends on presence-and-approval, codex-not-loaded, agents-view-polish; build
    order: last, after accepted-unread-notice.

## Decisions

- **D232 a loaded Codex task's waiting state is read from the ChatGPT app's follower snapshot.** Assumptions 1, 7, 8:
  discovery first; only with an owner, one follow → first snapshot → unfollow, all within the 2 s cap. Anything
  unexpected keeps today's answer (`running`).
- **D233 pending requests are classified by `method` only.** Assumptions 2, 3: the table above; `completed: true`
  skipped; unknown methods ignored; approval wins over input.
- **D234 the bridge reads two fields of the snapshot and keeps none of it.** Assumption 4: no conversation content in
  any store, log, detail, notice or result; `CodexIpc` gains a way to receive the one follower broadcast it asked for,
  and still drops every other broadcast.
- **D235 the presence code can send only discovery and the two follow broadcasts.** Assumptions 5, 6: never an approval
  decision; always unfollow.
- **D236 interface 2.6: Codex presence may be `waiting-approval` / `waiting-input`.** Assumption 10.

## Requirements

1. **First task, real host, read only, before any code**: on the test task, make one command (and, if possible, one file
   change and one user-input question) stop at the user's prompt, then follow the task once and record, from
   `conversationState.requests`, each entry's keys, `method`, `completed` and any time field — key names and types only,
   no values that carry conversation content — in the plan's notes. Also confirm: `following: false` ends the pushes;
   whether the broadcast send gets a `response` frame; snapshot size for the test task; whether a ping sent
   while the approval is pending queues behind it or is refused. The user approves any change to
   the test task's approval setting first. If the shape differs from assumption 2/3, stop and bring the spec back.
2. Red first, `bridge/test/` with a fake Codex IPC socket: an owner whose snapshot holds one pending
   `item/commandExecution/requestApproval` → `waiting-approval` with the fixed detail; `fileChange` and `permissions`
   likewise; `requestUserInput` → `waiting-input`; an approval and an input together → `waiting-approval`; only
   `completed: true` entries, an empty list, an unknown method, no `requests` key, a non-snapshot first change, no
   snapshot within the cap, an oversized frame → `running`; no owner → `stopped`; silent discovery → `not-loaded`
   (no follow sent); no socket → `unknown`.
3. Red first: every lookup sends `following: false` after `following: true` (also on timeout, error and oversized
   frame); the fake socket records every frame the presence code sends and the test asserts it is exactly
   `initialize`, `thread-owner-discovery` and the two follow broadcasts — never a decision method.
4. Red first: nothing from the snapshot other than the classification reaches the result — a snapshot whose items and
   request parameters contain a marker string; the marker appears in no tool result, `detail`, log line or file under
   the state directory.
5. Red first: `bridge_agents`, `bridge_send` (the existing `waiting-approval` warning now fires for a Codex recipient)
   and `bridge_outbox` `awaitingReply` show the new states; the whole lookup stays within the 2 s cap.
6. Docs: `docs/collaboration-interface.md` (`bridge_agents` presence), `docs/BACKGROUND-WAKE.md` (what Codex presence
   now reads), the `collab` skill if it lists presence values, CHANGELOG `[Unreleased]`, `interface.json` 2.6,
   `UPSTREAM.md` and manifest (D24).
7. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Always: read only towards the ChatGPT app; unfollow after every follow; interface changes are additions only.
- Ask first: any change to a Codex setting, even for the test task; every real-host test step that makes a command
  wait at a prompt.
- Never: send an approval, denial or any `thread-follower-*` decision; store, log or forward conversation content;
  create or touch test tasks in the user's working Codex projects; name a consumer project or session in any repo text,
  commit or PR; report `waiting-*` on a guess.

## Acceptance (coordinator, after release)

- On the test task, a command waiting at the user's prompt shows `presence: waiting-approval` in `bridge_agents` within
  one call; after the user answers it, the next call shows `running`. A message sent meanwhile carries the existing
  "waiting for the user's approval" warning.
- An idle loaded task shows `running`; a task not opened since the app started shows `not-loaded`, as before.
- No test leaves the app following the thread (no pushes after the call returns).

## Open questions

None left; resolved by the user 2026-10-19, as proposed:

1. `mcpServer/elicitation/request` counts as `waiting-input` (assumption 2).
2. No desktop notice for a Codex task waiting for approval in this module; `checkApprovals` stays Claude only, the
   decision inbox reminds its user; a notice can be a later module (assumption 11).
3. Snapshots over 8 MiB read `running`; the 8 MiB limit is not raised; task 1 records the test task's snapshot size
   (assumption 9).
4. The test task asks the user through a per-task setting if the app has one; otherwise the user makes and later
   reverts a temporary change to the test project's Codex config. Either way the user approves it first (assumption 13).
5. The release number is decided at release (assumption 12).
6. Task 1 checks whether a ping to a Codex task with a pending approval queues behind it or is refused; the existing
   `bridge_send` warning wording is adjusted in this module if Codex differs (Requirements 1, 5).
