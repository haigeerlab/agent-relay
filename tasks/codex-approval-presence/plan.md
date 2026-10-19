# Plan: codex-approval-presence

<!-- spec-guard: review approved -->

Based on [`spec/codex-approval-presence.md`](../../spec/codex-approval-presence.md) (accepted by the user on 2026-10-19:
assumptions 1–14 as drafted, D232–D236, the six open questions resolved as proposed). This branch carries the map row,
spec and plan as one PR; the implementation goes on `claude/codex-approval-presence-impl` from main after that PR is
merged. The release number is the user's call at release time. The round-2 coordinator is told every PR number.

## Task List

### Task 1: confirm the pending-request shape on the real host (read only)
Before any code. On the existing test Codex task in the dedicated test project only (never in the user's working Codex
projects), with a throwaway probe script in the session scratchpad (not in the repo):
- make the test task ask the user before a command runs: a per-task setting if the app has one, otherwise a temporary
  change to the test project's Codex config that the user makes and later reverts (open question 4) — **the user
  approves first**;
- let one command (and, if possible, one file change and one `requestUserInput` question) stop at the prompt, follow the
  task once, record for each `conversationState.requests` entry its keys, `method`, `completed` and any time field —
  names and types only, no values that carry conversation content — and the snapshot's size;
- confirm `following: false` ends the pushes, whether the broadcast send gets a `response` frame, and whether a ping
  sent while the approval is pending queues behind it or is refused (open question 6);
- the user answers the prompt themself; the probe never sends a decision.
Findings go into this plan's notes section and `todo.md`.

### Checkpoint (gate): shape matches the spec
If the entries do not match assumptions 2–3 (method names, `completed`), or following behaves differently, stop and
bring the spec back for review. If they match, the user confirms and the build continues; a ping-wording change for
`bridge_send` (open question 6) is folded into Task 5.

### Task 2: `CodexIpc` can send a broadcast and receive the one follower snapshot it asked for (D234, D235)
Red first in the new `test/local-ipc.test.ts` with a fake socket: `broadcast(method, params, targetClientIds)` writes a
`{type: "broadcast", …}` frame; a `thread-stream-state-changed` broadcast for the followed conversation resolves a
waiter with `params.change`; broadcasts for another conversation, other methods and unsolicited frames are still
dropped; an oversized frame closes the connection and rejects the waiter. Green: the smallest additions to
`local-ipc.ts`; the "never publish broadcasts" comment narrowed to say what is now read.

### Task 3: classify pending requests (D233)
Red first in `test/presence.test.ts`: the table of assumption 2 (three approval methods → `waiting-approval`,
`requestUserInput` and `mcpServer/elicitation/request` → `waiting-input`), `completed: true` skipped, unknown methods
ignored, approval wins over input, `since` only from a usable time field (per Task 1), a missing or non-array `requests`
→ no waiting state. Green: one pure function in `presence.ts` returning the state and the fixed English detail.

### Task 4: the Codex lookup follows, reads and unfollows within 2 s (D232, D234, D235)
Red first, fake socket: owner with a pending approval → `waiting-approval`; snapshot without `requests`, a first change
that is not a snapshot, no snapshot within the cap, an oversized frame → `running`; no owner → `stopped` with no follow
sent; silent discovery → `not-loaded` with no follow sent; no socket → `unknown`. Every follow is followed by
`following: false` (also on timeout, error, oversize); the frames the presence code sends are exactly `initialize`,
`thread-owner-discovery` and the two follow broadcasts. A marker string placed in the snapshot's items and request
parameters appears in no result, `detail`, log line or file under the state directory. The whole lookup ends within
the existing `AWAITING_PRESENCE_TIMEOUT_MS`. Green: `codexOwner`/`codexPresence` in `presence.ts` (or a successor
returning a `Presence` directly), keeping the owner client id from discovery.

### Task 5: the views (D232)
Red first through the MCP server: `bridge_agents` shows a Codex `waiting-approval`/`waiting-input` with its detail;
`bridge_send` to such a recipient carries the existing waiting warning (wording adjusted if Task 1 found Codex
differs); `bridge_outbox` `awaitingReply` shows it too, and its silent-app mapping to `unknown` is unchanged;
`checkApprovals` stays Claude only. Green: wiring in `server.ts` and `awaiting-reply.ts`.

### Checkpoint (report): bridge green
`npm run typecheck`, `npm test`.

### Task 6: interface 2.6, docs and bookkeeping (D236)
`interface.json` 2.6, `test_packaging`, `relay_status.py` docstring; `docs/collaboration-interface.md` (version line;
the `bridge_agents` presence text: since 2.6 a loaded Codex task may also be `waiting-approval` or `waiting-input`,
read from the app's own pending-request list, and a Codex `running` means none was seen or the list could not be read
within 2 s); `bridge/docs/BACKGROUND-WAKE.md`; `skills/collab` if it lists presence values; `UPSTREAM.md` row and
manifest (D24, regenerated after the last bridge edit); `bridge/CHANGELOG.md`; CHANGELOG `[Unreleased]` (schema 7
unchanged; runtime needs `upgrade --confirm`).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 7: PR and CI
Push `claude/codex-approval-presence-impl`, open the PR, tell the coordinator; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the release PR, which also waits for the user. Tell the Spec Guard
owner and the decision inbox that interface 2.6 ships. The real-host acceptance (spec "Acceptance") is asked first and
done on the test task after the upgrade.

## Notes

- Task 1 findings (real host, 2026-10-19, the existing test Codex task in the dedicated test project; key names and
  types only, from a throwaway read-only probe in the session scratchpad):
  - **Making a task ask the user**: the ChatGPT app has a per-task approval switch next to the composer ("请求批准" /
    "帮我批准" / "完全访问权限"); switching the test task to "请求批准" sets that thread's `approvalsReviewer` to `user`.
    No Codex config change was needed (open question 4: the per-task setting exists). The temporary trust entry and the
    project `.codex/config.toml` written for the test were removed; the global config matches its backup again, and the
    test task's switch is back on "帮我批准".
  - **A pending command approval**: `conversationState.requests` holds one entry with keys `method`, `id` (number) and
    `params`; `method` is `item/commandExecution/requestApproval` (matches assumption 2). The entry has **no `completed`
    key**. `params` keys: `kind`, `threadId`, `turnId`, `itemId`, `startedAtMs` (number), `environmentId`, `reason`,
    `command`, `cwd`, `commandActions`, `proposedExecpolicyAmendment`, `availableDecisions` — `reason`, `command` and
    `cwd` are conversation content, so only `method` and `params.startedAtMs` may be read (D234).
  - **A second signal**: while it waits, `conversationState.threadRuntimeStatus` is `{type: "active", activeFlags:
    ["waitingOnApproval"]}`; `{type: "active", activeFlags: []}` while working, `{type: "idle"}` after the turn.
  - **When the user answers** (the user declined): a patch replaces `requests` with `[]` (the entry is removed, not
    marked completed) and `activeFlags` is emptied; the turn ends and the task is `idle`.
  - **Stream**: the request arrives as a JSON-patch `add` on `requests` (`{type: "patches", baseRevision, revision,
    patches: [{op, path, value}]}`); the owner also re-sends whole snapshots now and then. No `response` frame answers
    the follow broadcast. After `following: false` no further frame for the thread arrived in the following 8 s (three
    runs). Snapshot size for the test task: 76–135 KB.
  - **Not checked**: a file-change approval and a `requestUserInput` question (only the command case was triggered),
    and whether a ping during a pending approval queues or is refused (the test task is not in the mailbox now).
  - An attempt by this session to click "decline" on the prompt was blocked by the session's permission check, as the
    spec's boundary requires; the user answered it.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The pending-request shape differs from what was inferred | wrong or missing waiting states | Task 1 confirms it on the real host before any code; a gate sends the spec back if it differs |
| Following the thread has a side effect in the ChatGPT app (stays followed, extra load, visible change) | the user's app behaves differently | always unfollow, also on error; Task 1 checks the pushes stop; only the test task is followed until release |
| Conversation content leaks into a result, log or file | privacy | only `method`/`completed` (and a time) are read; a marker-string test over results, logs and the state directory |
| The bridge sends something that answers a prompt | an action the user did not take | the presence code's sendable frames are pinned by a test; no decision method exists in the code |
| Large snapshots (long conversations) cost time or exceed 8 MiB | slower `bridge_agents`, lost waiting detail | the 2 s cap covers the whole lookup; oversize reads `running`; Task 1 records a real size |
| Several Codex agents in one `bridge_agents` call | each loaded one is followed once | lookups already run in parallel under the same cap; one follow per agent per call |
| The app's protocol changes in a later release | false states | unknown shapes read `running` (assumption 1); a wrong "waiting" is never guessed |
