# Spec: read-own-sent

## Objective

Third of the three modules of 0.7.1 (bridge). From the same usage report (`agent-relay-observer`, 2026-10-16) and the
user's decision: `bridge_inbox` with `messageId` refuses with `Message N is not in "<agent>"'s inbox` (13 calls). About
half read back a message the caller had sent itself; the rest read a message quoted in a body whose sender and
recipient were both someone else.

## What exists today (main d188a92, v0.7.0)

- `bridge_inbox` `messageId` (long-messages D152) uses `store.messagePart(agent, id)`, which accepts only a message
  delivered to `agent` (a direct message to it, or a broadcast it did not send), and pages the body with `bodyOffset`.
- A sender sees its own unacknowledged sends in `bridge_outbox` with a preview only, and status by id in
  `bridge_wake_status` / `bridge_wait` (ops-commands); none returns the full body of a sent message.
- Reads are not authenticated (inbox-read-receipt D99): anyone may list any agent's inbox; only the identity itself
  records the read. So a third party's message is not private from a determined caller; it is only not offered.

## Assumptions (accepted by the user 2026-10-16)

1. `bridge_inbox` with `agent: <caller>` and `messageId` also returns a message `agent` sent (direct or broadcast), in
   the same paged form with `bodyOffset`. No new parameter (sessions already open keep their tool definitions).
2. Reading one's own sent message records nothing: no read on the recipient's wake jobs, no activity refresh beyond
   what a read of the own inbox does today, and the result says it is a sent message (`direction: "sent"`; a received
   one is `"received"`, also new and optional).
3. When the message exists but `agent` is neither its sender nor a recipient, the refusal states the fact only, not
   privacy as a reason (user's wording relayed 2026-10-16: “这条消息不是发给你的，也不是你发出的；按编号只能读自己收到或
   发出的消息。要看原文，请问消息里的收件人或发件人。”), in English in the same sense: "Message #N was not sent to
   "<agent>" and not sent by it; by id an agent reads only messages it received or sent. For the text, ask its
   sender "<from>" or recipient "<to>"." It does not suggest reading another agent's inbox. A missing id says there is
   no such message.
4. Interface 2.1 → 2.2 (a wider read rule and one optional field); schema 6 unchanged. Release 0.7.1.

## Decisions

- **D212 a sender can read back its own messages by id.** Same tool, same paging; no read is recorded for anyone.
- **D213 a refused read by id says why and whom to ask.** Neither sender nor recipient: name both and suggest asking
  them; no such message: say so. The unauthenticated-read model (D99) is unchanged and not advertised.
- **D214 interface 2.2.** `docs/collaboration-interface.md`, `interface.json` and the packaging test move to 2.2;
  Spec Guard's `<3.0` range accepts it.

## Requirements

1. Red first, `bridge/test/`: the sender reads its own direct message and its own broadcast by id, including a second
   part via `bodyOffset`, with `direction: "sent"`; the recipient's read gives `direction: "received"`; reading one's
   own sent message leaves the recipient's wake jobs and `readAt` unchanged; a third-party id is refused naming sender
   and recipient and suggesting to ask them; a nonexistent id says no such message; expired messages follow today's
   rule for the reader's role.
2. `docs/collaboration-interface.md` (`bridge_inbox` row, version line), `interface.json` 2.2, packaging test,
   `skills/collab` (read one's own sent message by id).
3. CHANGELOG, `UPSTREAM.md` and manifest (D24); validate and CI green.

## Out of scope

- Read authentication, `bridge_outbox` full bodies, reading other agents' messages.

## Boundaries

- Never: record a read or acknowledge for a recipient because the sender read its own message.

## Acceptance (round-2 coordinator, after 0.7.1)

- A session reads back its own sent message by id; a third-party id gets the "ask its sender or recipient" refusal.
