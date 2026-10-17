# Plan: request-closing

Based on [`spec/request-closing.md`](../../spec/request-closing.md) (accepted by the user on 2026-10-17: assumptions
1–7, D216–D221, with D218 and D219 as written). This branch carries the map row, spec and plan as one PR; the
implementation goes on `claude/request-closing-impl` from main after that PR is merged. Only module of 0.8.0; the
release PR waits until the implementation PR is merged. The round-2 coordinator and the usage observer are told every PR
number.

## Task List

### Task 1: schema 7 and the closure rule (D216)
Red first in `test/schema.test.ts` (requirement 1): v7 creates `request_closures` from 6 and from an empty file; old
rows have no closure; a second open is a no-op. Green: `SCHEMA_VERSION = 7`, the v7 step in `schema.ts`, and
`OPEN_REQUEST` in `bridge-store.ts` gains "no closure row", so `owesReplies`, `awaitingReply` and
`totalAwaitingReply` follow it without further change.

### Task 2: `alsoAnswers` (D217)
Red first in the new `test/request-closing.test.ts`: one answer with `replyTo` A and `alsoAnswers` [B] closes both,
B's outbox entry carries `closedBy {kind: answered}` and the answer in `replies`, outcome `replied`, B counts as read by
its recipient; each refusal of D217 names the id and stores nothing (also the message itself is not stored); without
`replyTo` it still works; refused on a broadcast. Green: `SendInput.alsoAnswers`, validation and the closure rows in
`insertMessage`'s transaction (`bridge-store.ts`), the `replies` and `closedBy` queries, `MessageOutcome`, and the
`bridge_send` parameter in `server.ts`.

### Task 3: the other requester (D218)
Red first: in the twin case the other requester gets exactly one `bridge` notice on the request's thread with the
answer's id, recipient and a preview (one per requester and answer, even when it closes two of its requests), and `bridge_inbox {agent, messageId}` reads the answer with `direction: "answer"`;
no notice when the answer is addressed to that requester; a requester whose request was not closed by it still cannot
read it. Green: the notice in the same transaction as the closure; `messagePart` also admits the sender of a request the
message closed as `answered`.

### Task 4: `withdraws` (D219)
Red first: the sender withdraws its own open request addressed to this message's recipient → `withdrawn`, outcome
`withdrawn`, no read recorded, the recipient's `owesReplies` drops; refused for another's request, for a request to
another recipient, for a closed or linked one, and nothing is stored; `withdraws` with `expectsReply` in one message
works; a withdrawn request then named in `alsoAnswers` is refused ("withdrawn by #M"). Green in the same places as
Task 2.

### Checkpoint (report): bridge green
`npm run typecheck`, `npm test`; an acknowledgement still closes nothing (existing tests unchanged).

### Task 5: hooks, skills and instructions (assumption 4, D221)
`MAILBOX_SCHEMA_VERSIONS` adds 7 (doctor, `retire`, delegation backend tests on a schema 7 file); `collab` and
`session-routing` say to list every request an answer covers and to withdraw what is no longer needed; the server
instructions sentence; `bridge/INSTRUCTIONS.md`.

### Task 6: interface 2.3 and bookkeeping
`interface.json` 2.3 and `test_packaging`; `docs/collaboration-interface.md` (version line, `bridge_send`,
`bridge_outbox`, `bridge_wake_status`, `bridge_inbox` direction `answer`); `UPSTREAM.md` row and manifest (D24);
`bridge/CHANGELOG.md` and CHANGELOG `[Unreleased]` (plugins first, then `upgrade --confirm`; compatible-mode caveat;
rollback names schema 7).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 7: PR and CI
Push `claude/request-closing-impl`, open the PR, tell the coordinator and the observer; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.8.0 release PR, which also waits for the user. Tell the Spec Guard
owner that interface 2.3 ships.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A send passes validation but fails half-way | a closure without its message, or the reverse | message, closures and notice in one `atomically` step; a test forces a failure after the closures |
| `direction: "answer"` is a new value for read-own-sent's field | a consumer that only knows `sent`/`received` | documented as an addition in 2.3; the interface table says consumers treat unknown values as `received` |
| 0.7.x bridges keep running after the upgrade | their views still count closed requests | CHANGELOG caveat (D221); upgrade order plugins first, all bridges stopped before `upgrade --confirm` |
| Notice flood when one answer closes many twins | one notice per other requester | at most 20 ids per send; one notice per closed request, coalesced per requester and answer |
