# Spec: reply-own-message-guidance

## Objective

Second of the three modules of 0.7.1 (bridge). From the same usage report (`agent-relay-observer`, 2026-10-16) and the
user's decision ("第 2 条选 (b)"): senders who want to add to or correct a message they just sent pass
`replyTo: <their own message>` and are refused with `Only "<recipient>" … may reply` (15 calls; every one pointed at the
caller's own message, most bodies began with "补充" or "更正"). Once a `threadId` conflicting with the original's thread
was refused with `Message N has no thread`.

## What exists today (main d188a92, v0.7.0)

- `bridge/src/idempotency.ts` `assertMayReply` (identity-check assumption 5): only the recipient of a direct message
  may reply to it; a broadcast takes replies from anyone but its sender; `bridge` notices take none. The refusal to a
  sender says `"<sender>" may send a new message on the same thread instead` without naming the thread, and gives no
  way forward when the original has no thread.
- `replyThread` refuses a `threadId` other than the original's: `Message #N has no thread` / `is on thread "T"`, so its
  reply must be on the same thread … Omit threadId to use the original's thread.
- Since 0.7.0 a request marked `expectsReply` is open until any message links to it with `replyTo` (awaiting-reply-view
  D202), and a reply from the recipient is evidence of delivery (mailbox-polish D155). Letting senders link to their
  own messages would close their own requests and fake that evidence; option (a) was declined for this reason.

## Assumptions (accepted by the user 2026-10-16)

1. The rule stays: only the recipient replies (a broadcast: anyone but the sender).
2. A sender pointing `replyTo` at its own direct message or broadcast is refused with a way forward to copy: when the
   original is on a thread, "send a new message to <recipient> with threadId "<T>" and no replyTo"; when it has none,
   "send a new message to <recipient> without replyTo and start the body with 补充 #N / addendum to #N" — the bridge
   does not invent a thread.
3. The thread-mismatch refusal also names what to do: omit `threadId` (as today), and says the original's thread
   (or that it has none).
4. Wording only; no schema or interface change. Release 0.7.1 with the other two modules.

## Decisions

- **D211 a sender may not reply to its own message; the refusal says how to add to it instead.** Keeps D155 and D202
  intact; the guidance names the original's thread or, when there is none, says to send a new message that cites #N.

## Requirements

1. Red first, `bridge/test/`: `bridge_send` with `replyTo` at the caller's own direct message on thread T is refused
   with text containing the recipient, `threadId "T"` and `without replyTo` (or equivalent agreed wording); on a
   message without thread the text says to send a new message citing #N and contains no `threadId`; the caller's own
   broadcast gets the same guidance with recipient `*`; a third party (neither sender nor recipient) keeps the
   current refusal; the recipient's reply still works; following the guidance succeeds and leaves the original's open
   request open in `awaitingReply`.
2. Red first: a `threadId` that differs from the original's gives the original's thread or "has no thread" and
   "omit threadId".
3. `skills/collab` and `skills/session-routing`: to add to one's own message, send a new message on its thread (or
   citing #N), never `replyTo` to oneself.
4. CHANGELOG, `UPSTREAM.md` and manifest (D24); validate and CI green.

## Out of scope

- Option (a) (self-`replyTo` as an append), editing or retracting sent messages.

## Boundaries

- Never: let a non-recipient's message count as a reply, delivery evidence or the close of an open request.

## Acceptance (round-2 coordinator, after 0.7.1)

- A session that tries `replyTo` on its own message gets the guidance and follows it without asking the user.
