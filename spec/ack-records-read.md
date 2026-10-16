# Spec: ack-records-read

## Objective

First module of 0.6.10 (bridge). Item 2 of a seven-item list relayed on 2026-10-16 by a Codex monitoring session
(mailbox name `spec-guard-monitor`) with the user's consent; the user chose items 2, 3 and 7 for 0.6.10 the same day
("可以，按你的建议排，先做 0.6.10"; "确认，七条假设通过"; "去掉 held-notice-early，0.6.10 只做前三个").

Problem: a recipient that handles a message from its wake preview and acknowledges it with `bridge_ack` without calling
`bridge_inbox` leaves `messages.read_at` empty (seen on #1317 and #1320), so the sender's view says "acknowledged" and
"not read" at once, and upper layers misjudge it as unread.

## What exists today (main 7a2af10, v0.6.9)

- `BridgeStore.ack` inserts acknowledgements and closes the wake job (`ack-wake-atomic` D130), in one transaction.
- `read_at` is set only by `WakeQueue.recordRead` (inbox reads, `bridge_thread`, and a reply to the sender's own
  message).

## Assumptions (accepted by the user 2026-10-16)

1. A message newly acknowledged by its recipient gets `read_at` set if it was empty, in the same transaction as the
   acknowledgement; a `read_at` already set is kept.
2. Only messages this call acknowledges change (an id already acknowledged, or not delivered to the agent, changes
   nothing). Broadcasts keep today's behaviour (`read_at` belongs to direct messages).
3. Release with the other two modules as 0.6.10; bridge change, `upgrade --confirm`; schema 5 unchanged.

## Decisions

- **D197 acknowledging a message also records that it was read, when that was not recorded yet.**

## Requirements

1. Red first, `bridge/test/`: ack without a prior inbox read sets `read_at` (and the outbox shows the message as read
   and acknowledged); an earlier `read_at` is kept; a repeated ack, an ack by another agent and an ack of a
   broadcast change no `read_at`.
2. Bookkeeping in the same commit (D24): `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]`.
3. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; CI green.

## Boundaries

- Never: change acknowledgement rules or wake closure; touch a message another agent owns.
