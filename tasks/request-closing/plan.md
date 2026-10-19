# Plan: request-closing

Based on [`spec/request-closing.md`](../../spec/request-closing.md) (accepted by the user on 2026-10-17: assumptions
1–8, D216–D222, with D218 and D219 as written; assumption 8 and D222 from the round-2 review of #129, accepted the
same day). This branch carries the map row, spec and plan as one PR; the
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
`replyTo` it still works; refused on a broadcast; `closed` in the result (D222); the same key and list retried →
`duplicate: true` and no second closure, a different list → refused; two `BridgeStore` instances on one file
committing alternately cannot close one request twice, and the loser gets the readable refusal. Green: `SendInput.alsoAnswers`, validation **after** the idempotency check and the closure rows inside
`deliver()`'s `BEGIN IMMEDIATE` transaction (`bridge-store.ts`), the primary-key conflict turned into the refusal,
`contentDifferences` comparing the lists (`idempotency.ts`), the `replies` and `closedBy` queries, `MessageOutcome`, and the
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
works; a withdrawn request then named in `alsoAnswers` is refused ("withdrawn by #M"), but a `replyTo` on it is
allowed, outcome `replied`, `closedBy` withdrawn (D220); retry and two-store cases as in Task 2. Green in the same
places as Task 2.

### Checkpoint (report): bridge green
`npm run typecheck`, `npm test`; an acknowledgement still closes nothing (existing tests unchanged).

### Task 5: hooks, skills and instructions (assumption 4, D221)
`MAILBOX_SCHEMA_VERSIONS` adds 7 (doctor, `retire`, delegation backend tests on a schema 7 file); `collab` and
`session-routing` say to list every request an answer covers, to withdraw what is no longer needed, and to trust
`closed` (no `closed` = a bridge older than 0.8.0, nothing closed, D222); the server
instructions sentence; `bridge/INSTRUCTIONS.md`.

### Task 6: interface 2.3 and bookkeeping
`interface.json` 2.3 and `test_packaging`; `docs/collaboration-interface.md` (version line, `bridge_send`,
`bridge_outbox`, `bridge_wake_status`, `bridge_inbox` direction `answer`, `bridge_send` result `closed`); `UPSTREAM.md` row and manifest (D24);
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
| A 0.8.0 session talks to a 0.7.x bridge during the upgrade | its `alsoAnswers` is dropped silently | `closed` in the result (D222); acceptance checks it on the real host |
| Notice flood when one answer closes many twins | one notice per other requester | at most 20 ids per send; one notice per closed request, coalesced per requester and answer |

## Revision 2026-10-19: already-closed requests are skipped (spec "Revision 2026-10-19", D237–D239)

Branch `claude/closed-request-skip` from main 1f1aea9 (v0.8.4). Bridge, skills and docs; schema 7 unchanged; interface
2.7; released as 0.8.5 in a separate release PR.

### Task 8: skip instead of refuse in the store (D237, D238)
Red first in `bridge/test/request-closing.test.ts`, one case per requirement 1 bullet: withdrawn, answered by
`replyTo`, answered by another `alsoAnswers`, `failed`, overdue (`expired`), `withdraws` of an answered request, a mix
(open ones closed, closed ones skipped, D218 notice and D155 read only for the closed ones), wrong ids still refused
with nothing stored, a duplicate retry with `skipped: []`, and the lost race (closure inserted between check and
insert). Then in `bridge-store.ts`: `assertClosable` returns `null` or a `{id, reason, by?}` skip for the state checks
and still throws for the identity and type checks; `deliver` filters the skipped ids out before `closeRequests`,
`recordRead` and `noticeOtherRequesters`; `closeRequests` turns a primary-key conflict into a skip; `deliver` returns
`skipped` (sorted by id). `idempotency.ts` unchanged.

### Task 9: `bridge_send` result and skills (D238, requirement 2, 3)
Red first: an MCP test that `bridge_send` with a withdrawn id in `alsoAnswers` returns `skipped` and a delivered
message. Then `server.ts` adds `skipped` to the result whenever `alsoAnswers` or `withdraws` was given, and the
parameter descriptions say an already closed id is skipped; `collab`, `session-routing`, the server instructions and
`INSTRUCTIONS.md` say a skipped id was already closed (nothing to redo) and a missing `skipped` means an older bridge.

### Task 10: interface 2.7 and bookkeeping (D239, requirement 4)
`interface.json` 2.7, `test_packaging`, `relay_status.py` docstring, `docs/collaboration-interface.md` (version line,
`bridge_send` row with `skipped` and the refusal list), `UPSTREAM.md` row and manifest, `bridge/CHANGELOG.md` 0.8.5,
CHANGELOG `[Unreleased]` (plugins and runtime in either order; runtime needs `upgrade --confirm`).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 11: PR and CI
Push, open the PR, ask the round-2 coordinator to review; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.8.5 release PR, tag and real-host upgrade, each with the user's
approval; tell the reporting session when 0.8.5 ships (no consumer upgrade during its freeze).

### Risks (revision)

| Risk | Impact | Mitigation |
|---|---|---|
| A real wrong id now slips through as a skip | a sender believes it closed something it did not | only state checks skip; identity and type checks still refuse; `skipped` names every skipped id and why |
| Skip filtering misses a path (read, notice) | a skipped request is marked read or its sender is notified | the mix test asserts no read and no notice for skipped ids |
| A session on 0.8.5 skills talks to a 0.8.4 bridge | its send is refused as before | skills say a refusal naming a closed request means an older bridge; resend without that id |
