# Spec: request-closing

## Objective

Only module of 0.8.0 (bridge, hooks, skills). Since 0.7.0 a message marked `expectsReply` stays open until a message
links to it with `replyTo`, and `owesReplies` / `bridge_outbox awaitingReply` count it until then. A usage observation
on 2026-10-17 found that the count only grows: one reviewer showed 13 open requests it had in fact answered. The user
decided on 2026-10-17 to let one answer close several requests, let a sender withdraw its own request as a separate
state, and tighten the guidance ("按 (a) 写 spec … schema 7、接口 2.3、出 0.8.0。假设没问题").

Readers: the user; the round-2 coordinator and the usage observer (review, re-check after release); the Spec Guard
owner (interface 2.3 is within its accepted `>=1.0,<3.0`).

## What exists today (main b3beffd, v0.7.2)

- `bridge-store.ts` `OPEN_REQUEST`: marked, direct, not `failed`/`expired`, recipient not retired, and **no message with
  `reply_to` = its id**. An acknowledgement does not close it (D202). `messages.reply_to` holds one id.
- `idempotency.ts` `assertMayReply`: only the recipient of a direct message may link to it; the reply may be addressed to
  anyone. D211 kept senders from linking to their own messages because that "would close their own requests and fake
  that evidence" (a reply from the recipient is delivery evidence, D155).
- `MessageOutcome` = `pending | acknowledged | replied | failed | expired`; `bridge_outbox` entries carry `replies`.
- Hooks accept `MAILBOX_SCHEMA_VERSIONS` `(2, 3, 4, 5, 6)`; since 0.7.0 every hook that meets a newer schema says
  "update the agent-relay plugin" (D208). A 0.7.x bridge opens a newer mailbox in compatible mode.

Measured on the real mailbox (read only, 2026-10-17, all requests since 0.7.0 went live on 2026-10-16 13:46 UTC):
144 marked requests, 88 linked, **53 open, all addressed to one reviewer**; 52 of the 53 have no `threadId`.

| Cause | Open | Example |
|---|---|---|
| Two senders asked the same recipient within 10 minutes; the answer linked to the other request | 18 | #3898 / #3900 → #3903 links #3900 only |
| Two senders asked; the answer linked to neither | 23 | #3855 / #3858 → #3861, `replyTo` null |
| The answer went to a third party and linked that party's request; the body names this one | 12 | #4006 → #4011 links #4010 and says "FE #4006" |

All time, 45 of the 144 requests had such a twin. A request the sender no longer needs (#3858 after #3863) cannot be
closed at all.

## Assumptions (accepted by the user 2026-10-17)

1. **One answer can close several requests.** `bridge_send` gains an optional `alsoAnswers: number[]`: besides
   `replyTo`, the message answers these requests. Each must be a direct marked request addressed to the sender, the same
   rule as `replyTo`. `replyTo` stays a single number, so consumers that read it as a number keep working.
2. **Schema 7.** One message can now close several requests, so the links go in a new table (additive migration).
   Interface 2.2 → 2.3 (additions only). Released as **0.8.0**.
3. **A sender can withdraw its own request, recorded as withdrawn, never as answered** (D211's reason stands).
   `bridge_send` gains an optional `withdraws: number[]`: only the sender's own open marked requests. No new tool: the
   server keeps ten. `awaitingReply` and `owesReplies` stop counting withdrawn requests.
4. **Guidance**: when one answer covers several requests, list them all; answer every `expectsReply` with `replyTo`.
   Skills (`collab`, `session-routing`), the server instructions and `bridge/INSTRUCTIONS.md`.
5. **No backfill**: the requests already open stay open; nothing is inferred from message text. After the upgrade the
   recipient or the sender may close them with the new parameters.
6. **Not in scope**: an acknowledgement as an answer, automatic expiry of delivered requests by age, inferring from text.
7. **Compatibility is checked here**, not assumed: which 0.7.x parts read schema 7 and what they say (D208).
8. **Review additions (round-2 review of #129, accepted by the user 2026-10-17)**: validation inside the write
   transaction with conflicts as readable refusals; validation after the idempotency check, and the two lists in the
   retry comparison; `bridge_send` echoes what it closed (`closed`); `replyTo` on a withdrawn request is allowed and
   wins the outcome; the D218 notice wakes like other notices; D35 covers `replyTo` only.

## Decisions

- **D216 closures live in their own table.** Schema 7 adds `request_closures(request_id INTEGER PRIMARY KEY, message_id
  INTEGER NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('answered', 'withdrawn')), closed_at TEXT NOT NULL)`: at most one
  closure per request, written in the same transaction as the closing message. `replyTo` keeps working through
  `messages.reply_to` and is not copied into the table. `OPEN_REQUEST` adds "and no row in `request_closures`".
- **D217 `alsoAnswers` (assumption 1).** Up to 20 distinct ids, none equal to `replyTo`. Each must exist, be a direct
  message addressed to the sender with `expectsReply`, and be still open (not linked by `replyTo`, not closed, not
  `failed`/`expired`). Any id that fails refuses the whole send before anything is stored, naming the id and the reason
  (`already answered by #M`, `withdrawn by #M`, `addressed to "X"`, `not a request`, `no message #N`). Works with or
  without `replyTo`; not on a broadcast. Each closed request counts as read by its recipient (as a `replyTo` does, D155)
  and gets `kind: 'answered'`. **Where the checks run:** inside `deliver()`'s `BEGIN IMMEDIATE` transaction, never
  before it (every session has its own bridge process on one SQLite file), and **after** the idempotency check, so a
  retry of a send that already closed B returns the stored message (`duplicate: true`) instead of refusing itself. Two
  processes closing one request at once (an answer and a withdrawal) cannot both win: `request_id` is the primary key,
  and the loser's constraint error becomes the same readable refusal (`already answered by #M`, `withdrawn by #M`) with
  the whole send rolled back, never a raw SQLite error. The idempotency comparison (`contentDifferences`) includes
  `alsoAnswers` and `withdraws` (as sorted lists): the same key with a different list is refused like a different body.
  D35 (one stored reply per `replyTo`) covers `replyTo` only; a repeated `alsoAnswers`-only answer is stopped by the
  idempotency key or by "already answered".
- **D218 the other requester hears of it.** When `alsoAnswers` closes a request whose sender is not the
  answer's recipient (the twin case), that sender would otherwise never see the answer. The bridge sends it one notice
  from `bridge`, on the request's thread: "Your request #N to "R" was answered by #M (sent to "X")", with a preview of
  the answer, and the answer becomes readable by id to that sender (`bridge_inbox messageId`, as for its sender and
  recipient, D212). No notice when the answer already goes to that sender. Notices from `bridge` are not answered; the
  notice pings its recipient under the rules every bridge notice follows (bound and not retired).
- **D219 `withdraws` (assumption 3).** Up to 20 distinct ids. Each must be the sender's own open marked direct request
  **addressed to this message's recipient**, so the withdrawal itself tells the recipient (one withdrawal message per
  recipient). Refusals as in D217 (`sent by "X"`, `addressed to "Y"`, …). Allowed in the same message as
  `expectsReply` (withdraw the old request, ask the new one). Not delivery evidence; records no read. Checked where and
  when D217's checks run, with the same conflict and retry rules.
- **D220 the views.** `bridge_outbox` entries gain `closedBy: {messageId, kind}` when a closure exists; an
  `alsoAnswers` answer also appears in `replies`. `bridge_wake_status {messageId}` outcome gains `withdrawn`
  (`replied` covers an `alsoAnswers` answer). `owesReplies`, `awaitingReply` and `totalAwaitingReply` follow
  `OPEN_REQUEST`. Within 2.x these are additions; a consumer treats an outcome it does not know as `pending`.
  **A reply wins:** the recipient may still answer a withdrawn request with `replyTo` (a reply is not only an answer to a
  request, D36); the outcome is then `replied`, and `closedBy` keeps the recorded `{kind: withdrawn}`. Withdrawing a
  request that already has a `replyTo` is refused (it is no longer open).
- **D222 `bridge_send` says what it closed.** The result carries `closed: [{id, kind}]` whenever `alsoAnswers` or
  `withdraws` was given (empty only on a duplicate retry that closed nothing new — it then lists what the stored message
  closed). A 0.7.x bridge drops unknown parameters silently (zod strips them; measured), so during an upgrade a new
  session talking to an old bridge would believe it closed requests it did not. The skills say: after `alsoAnswers` or
  `withdraws`, trust `closed` in the result; no `closed` field means the bridge is older than 0.8.0 and nothing was
  closed.
- **D221 interface 2.3, schema 7, plugins first.** `interface.json` 2.3; the interface document lists `alsoAnswers`,
  `withdraws`, `closedBy`, `closed`, outcome `withdrawn`; `MAILBOX_SCHEMA_VERSIONS` becomes `(2, … , 7)`; the rollback caveat
  names schema 7. Upgrade order as D208: plugins on both hosts first, then `upgrade --confirm`. A 0.7.x bridge still
  running beside a schema 7 mailbox (compatible mode) ignores closures, so its views still count closed requests until
  it is restarted; the CHANGELOG says so.

## Requirements

1. Red first, `bridge/test/schema.test.ts`: v7 adds `request_closures` (from 6 and from an empty file); old rows have
   no closure.
2. Red first, a new `bridge/test/request-closing.test.ts`:
   - one answer with `replyTo` A and `alsoAnswers` [B] closes A and B; `owesReplies` and `awaitingReply` drop both;
     B's outbox entry has `closedBy {kind: answered}` and the answer in `replies`; outcome `replied`;
   - every refusal in D217, and nothing is stored when one id fails; the same for D219;
   - twin case (D218): B from another sender → that sender gets one `bridge` notice and can read the answer by id; no
     notice when the answer is addressed to B's sender;
   - `withdraws` closes the sender's own request as `withdrawn`, outcome `withdrawn`, no read recorded, the recipient's
     `owesReplies` drops; a sender cannot withdraw another's request; withdrawn and then answered with `alsoAnswers` →
     refused; withdrawn and then answered with `replyTo` → allowed, outcome `replied`, `closedBy` withdrawn;
   - two `BridgeStore` instances on one file: one answers B with `alsoAnswers` while the other withdraws B; exactly one
     wins, the other gets the readable refusal and stores nothing (D217);
   - the same idempotency key and list retried → `duplicate: true`, no second closure, `closed` lists the stored
     closures; the same key with a different list → refused (D217, D219);
   - `closed` in the result lists exactly what was closed (D222);
   - an acknowledgement still closes nothing.
3. `server.ts`: the two parameters with descriptions, `closed` in the result (D222); the instructions sentence
   (assumption 4).
4. Hooks: `MAILBOX_SCHEMA_VERSIONS` adds 7; doctor, `retire` and the delegation backend pass on schema 7.
5. Skills `collab` and `session-routing`: list every answered request; withdraw what is no longer needed; trust `closed`
   and treat its absence as an old bridge (D222);
   `bridge/INSTRUCTIONS.md` the same (D24 bookkeeping).
6. Interface 2.3 docs, `interface.json`, `test_packaging`; CHANGELOG `[Unreleased]` with upgrade order and the
   compatible-mode caveat.
7. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Always: tests first; closures only through the two parameters; one closure per request.
- Ask first: closing requests already open on the real mailbox; any automatic closing; any change to who may `replyTo`.
- Never: infer an answer from text; count an acknowledgement or a withdrawal as an answer; let anyone but the recipient
  answer or anyone but the sender withdraw.

## Acceptance (after 0.8.0)

- On the real host: a twin pair answered once with `replyTo` + `alsoAnswers` leaves neither in the reviewer's
  `owesReplies`, and the other requester gets the notice; a sender withdraws a stale request and it leaves both views,
  with outcome `withdrawn`.
- During the upgrade window, a 0.8.0 session talking to a still-running 0.7.x bridge sends `alsoAnswers` and sees no
  `closed` in the result, so it knows nothing was closed (D222); the request stays open.
- doctor ok on schema 7; Spec Guard still accepts interface 2.3.

## Open questions

- None. D218 (notify the other requester, answer readable by id) and D219 (a withdrawal goes to the requests'
  recipient) were accepted by the user as written on 2026-10-17.
