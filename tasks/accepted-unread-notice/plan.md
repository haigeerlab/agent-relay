# Plan: accepted-unread-notice

<!-- spec-guard: review pending -->

Based on [`spec/accepted-unread-notice.md`](../../spec/accepted-unread-notice.md) (accepted by the user on 2026-10-17:
assumptions 1–10 including 4(c), D228–D231, and the four details chosen in the spec: the 24-hour window, the field
names `wake.doubt` and `waiting.doubtfulIds`, the sender message and outbox marker staying when desktop notices are off,
the real-host check with a test Codex task; assumption 11 from the round-2 review of #135, #4998: options (b) and (c)
for an unrecorded read in a new bridge process, the job's own target, how the test task's bridge is found, the known
limit of the sender message). This branch carries the map row, spec and plan as one PR; the
implementation goes on `claude/accepted-unread-notice-impl` from main after that PR is merged. Only module of 0.8.2; the
release PR waits until the implementation PR is merged. The round-2 coordinator and the usage observer are told every
PR number.

## Task List

### Task 1: the doubtful-delivery query (D228)
Red first in the new `test/accepted-unread.test.ts` against the store with a fake clock: a direct message whose Codex
wake job is `accepted`, unread and unacknowledged is returned once five minutes have passed since
`delivery_changed_at`, not at 4 min 59 s; it is not returned once read (`read_at`, job `read`), acknowledged, expired,
accepted more than 24 hours ago, without an accepted time, or when the job's own target is Claude; a job whose own
target is Codex counts even if the recipient is now bound to Claude, and the reverse does not (the job decides). Green: one store method (e.g.
`wakes.acceptedUnread(now)`) returning `{messageId, agent, fromAgent, threadId, acceptedAt}`, and
`ACCEPTED_UNREAD_AFTER_MS = 5 * 60_000` plus the 24-hour window next to the other thresholds in `notify.ts`.

### Task 2: the desktop notice (D229)
Red first, same file, with the notice log: the dispatcher's 30-second tick raises one `accepted-unread` notice per
doubtful message (naming message, sender, recipient and both possible causes — a closed connection, or a read before registering
again — no click arguments, preview per D89); a second tick and a second
dispatcher on the same mailbox add none; `notify.off` and `AGENT_RELAY_NOTIFY=off` silence it. Green: a
`checkAcceptedUnread()` on the same tick as `checkApprovals` (a separate call: `checkApprovals` returns early when no
Claude session waits), notice kind `accepted-unread` in `notify.ts` with the mark `accepted-unread-<message id>`.

### Task 3: the sender message (D230, part 1)
Red first: one `bridge` message to the sender per doubtful message, in the original thread, idempotency key
`accepted-unread:<message id>`, also with two dispatchers ticking; none when the sender is `bridge`, the recipient,
unknown or retired; sent even with desktop notices off. Green: the body in `notices.ts` next to
`deliveryFailureNotice`, sent from `checkAcceptedUnread()`.

### Task 4: the views (D230, part 2)
Red first through the MCP server: `bridge_outbox` and `bridge_wake_status` show `wake.doubt: {reason:
"accepted-unread", since}` and the added detail sentence only while the condition holds and drop it once the recipient
reads or acknowledges; `bridge_agents` shows `waiting.doubtfulIds` (oldest first, at most 20) likewise; every other
field and an ordinary accepted message are unchanged. Also through the MCP server, a new bridge process: the recipient's
first `bridge_inbox` before registering again returns `readRecorded: false` and leaves the message doubtful after five
minutes (the notice names the unrecorded read as a possible cause); registering again and reading once more clears it.
Green: computed on read in `bridge-store.ts` from the same
condition as Task 1.

### Checkpoint (report): bridge green
`npm run typecheck`, `npm test`.

### Task 5: interface 2.5, docs and bookkeeping (D231)
`interface.json` 2.5, `test_packaging`, `relay_status.py` docstring; `docs/collaboration-interface.md` (version line;
`wake.doubt` in `bridge_outbox` and `bridge_wake_status`; `waiting.doubtfulIds` and the assumption 10 wording in the
`bridge_agents` row: `lastSeen`/`lastActivity`, what `running` does not promise, when `waiting` and `owesReplies` clear,
the missing full stop); `docs/BACKGROUND-WAKE.md`; `skills/collab` (what a doubtful delivery means, what to tell the
user; a read returning `readRecorded: false` with a `readNote` asking to register: register again, read once more); `UPSTREAM.md` row and manifest (D24, regenerated after the last bridge edit); `bridge/CHANGELOG.md` 0.8.2;
CHANGELOG `[Unreleased]` listing "new marker" and "clarified meaning" separately (schema 7 unchanged; runtime needs
`upgrade --confirm`).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 6: PR and CI
Push `claude/accepted-unread-notice-impl`, open the PR, tell the coordinator and the observer; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.8.2 release PR, which also waits for the user. Tell the Spec Guard
owner that interface 2.5 ships. The real-host acceptance (a test Codex task whose bridge process was ended) is asked
first and done by the coordinator after the upgrade.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A task read in a new bridge process before registering again, so the read was not recorded | a false notice right after an upgrade or restart | the `collab` skill tells it to register and read again; the notice names this cause; tested and in the acceptance (round-2 review of #135) |
| A Codex task legitimately does not read for five minutes after its turn starts | a false notice and sender message | measured: none of 1893 accepted pings fell between 3 and 5 min; once per message; the marker disappears once it reads |
| Several bridges tick at once | duplicate notices or sender messages | the `notified/` mark for the desktop notice and the store's idempotency key for the sender message; tested with two dispatchers |
| Old accepted jobs flood notices right after the upgrade | many stale notices | the 24-hour window; the only accepted job on the real mailbox today is acknowledged and has no accepted time |
| The extra query on every tick and every view | slower listings | it reads only `accepted` Codex jobs from the last 24 hours (a handful); index `wake_jobs(state, retry_at)` already leads with state |
