# Spec: rewake-on-return

## Objective

Third module of 0.6.10 (bridge). Item 3 of the same list: messages whose ping expired while the recipient was not
running stay unread after the recipient comes back, until the user tells it to read them.

## What exists today (main 7a2af10, v0.6.9)

- Each message has one wake job (`UNIQUE(message_id, agent)`). A job pending as `offline` (or without a reason) expires
  one hour after it was created (`OFFLINE_WAKE_WINDOW_MS`); `busy` after 24 hours. The message stays in the inbox; the
  sender gets one failure notice (`notified_at`).
- Evidence (read-only, real mailbox): #1353, #2189, #2204, #2234, #2238 to Claude recipients expired as `offline`
  after 4–63 attempts; #2234 and #2238 were read only after the user told the recipient to. No Claude wake job was ever
  `held` (so these were stopped sessions, not Bypass holds).
- `bridge_register` returns `unread` and `next: "N unread message(s) are waiting…"`.
- The dispatcher checks live Claude sessions every 30 seconds (`checkApprovals`, D148) from the session registry,
  which carries each process's start (`procStart`, the same text `ps -o lstart=` prints under `TZ=UTC`).

## Assumptions (accepted by the user 2026-10-16)

1. **Re-arm, not a new job:** an `expired` wake job whose message is still unhandled (not acknowledged, not read) and
   not expired itself (its queue timeout has not passed) goes back to `pending`, created now, with the agent's
   current wake target and a plain detail saying it was pinged again after the recipient came back. Retry rules and
   durable ordering are unchanged; the sender is not notified a second time if it expires again.
2. **Trigger 1, any host:** `bridge_register` by the recipient re-arms its expired jobs (only when it has a wake
   binding) and its result says how many unread messages had an expired ping and were pinged again.
3. **Trigger 2, Claude:** when the periodic check sees a live session bound for an agent whose job expired before that
   process started, it re-arms the agent's expired jobs. A job re-armed after that start is newer than the process, so
   one process start re-arms at most once.
4. Messages expired by their queue timeout (24 h default) are not re-armed.
5. Release with the other two modules as 0.6.10; bridge change, `upgrade --confirm`; schema 5 unchanged.

## Decisions

- **D199 a recipient that comes back (registers again, or a Claude session process started after its pings expired)
  gets its still-unhandled messages pinged once more.**

## Requirements

1. Red first, wake-queue/store tests: re-arm resets state, created time, attempts, retry time and target; skips
   acknowledged, read, expired-message and non-expired jobs; the sender's `notified_at` stays, so no second notice.
2. Red first, register: result counts the re-armed messages in `next`; no wake binding → nothing re-armed, the count is
   still reported.
3. Red first, dispatcher: a live Claude session whose process started after the expiry → re-armed once; a process
   started before the expiry → not; a second check after re-arming → nothing more.
4. `docs/BACKGROUND-WAKE.md`, CHANGELOG, `UPSTREAM.md` and manifest (D24).
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Never: start or resume a stopped session from the bridge; re-arm a message the recipient already handled or read;
  ping more than once per process start.

## Acceptance (coordinator, after 0.6.10)

- A message to a stopped Claude session expires; opening that session gets it pinged within about 30 seconds.
