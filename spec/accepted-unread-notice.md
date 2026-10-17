# Spec: accepted-unread-notice

<!-- spec-guard: review approved 55c59e9a0fd2 -->

## Objective

Only module of 0.8.2 (bridge, docs). From a report relayed on 2026-10-17 and the user's decision the same day ("十条假设
全部通过，包括 4(c) 和第 10 条"): during the 0.8.0 upgrade every bridge process was ended, as the upgrade steps say. A
Codex task lost its mailbox connection ("Transport closed"). Another bridge then woke it through the ChatGPT app, the
app answered "Codex confirmed a new turn" and the ping became `accepted`, but in that turn the task could not call any
mailbox tool. The message waited about 16 minutes, until the user restarted ChatGPT. The sender and the patrol view saw
"delivered, recipient running" the whole time.

The bridge cannot see a Codex task's MCP connection: presence only asks the app whether the task is loaded
(codex-not-loaded D200). The one signal left is "accepted, and still not read long afterwards".

The same module also writes down, in the interface document, what the `bridge_agents` fields an upper layer reads
actually mean (assumption 10; a suggestion from the Spec Guard monitoring session the user agreed to fold in).

Readers: the user; the round-2 coordinator and the usage observer (review, re-check after release); the Spec Guard owner
(interface 2.5 is within its accepted `>=1.0,<3.0`).

## What exists today (main cb5e3d8, v0.8.1)

- `bridge/src/wake-dispatcher.ts` `drain` claims a pending wake job, dispatches it and finishes it. A job that ends
  `accepted` is never looked at again. Fetching the message moves it to `read` (`wake-queue.ts`, "Recipient fetched
  the mailbox message"), `bridge_ack` to `acknowledged`. `accepted` is terminal for the message's delivery state and
  never expires (delivery-state-machine).
- D67 (codex-gated-wake) notifies the user about a Codex ping that is offline or held at once, and about a busy one
  after ten minutes (`BUSY_NOTIFY_AFTER_MS`), once per message, through `notifyUndelivered` with the `notified/` marks.
  D193 (claude-offline-notice) does the same for an offline Claude recipient after five minutes
  (`CLAUDE_OFFLINE_NOTIFY_AFTER_MS`). Neither looks at an `accepted` job.
- Every bridge runs `checkApprovals` every 30 seconds (D148, D199).
- Senders are told about failed pings by `sweepDeliveryFailures` (`notices.ts`): a message from the reserved agent
  `bridge`, deduplicated by the store's idempotency key, skipped when the sender is `bridge`, the recipient itself, or
  retired.
- For a direct message, `messages.delivery_changed_at` holds when it became `accepted` and `read_at` when it was first
  fetched. Broadcasts have no wake jobs.
- `bridge_outbox` and `bridge_wake_status` show `wake: {state, detail, pendingReason?}`. `bridge_agents` shows
  `waiting: {count, from, ids, oldestAt}` and the Codex task's `presence.state` (`running` when the app has it loaded).
- **Measured on the real mailbox (read only, 2026-10-17).** Time from `accepted` to the first read or ack:

  | Host | accepted | ≤ 1 min | 1–3 min | 3–5 min | 5–10 min | 10–20 min | > 20 min |
  |---|---|---|---|---|---|---|---|
  | Claude | 1469 | 1469 | 0 | 0 | 0 | 0 | 0 |
  | Codex | 1893 | 1878 | 6 | 0 | 3 | 3 | 3 |

  Six of the nine Codex messages over five minutes were sent within minutes of a runtime upgrade (upgrade stamps
  `runtime.previous-<UTC>`): #1394 8.9 and #1395 11.9 min (upgrade 10-15 08:24Z), #3094 18.2 min (10-16 07:46Z), #3978
  9.4 and #3994 8.4 min (10-16 16:05Z), #4627 16.0 min (10-17 07:09Z, the reported case). The other three (#382, #405,
  #1014) were read 30 to 70 hours later and never acknowledged. The six slow ones between one and three minutes have no
  upgrade nearby. The only wake job still `accepted` today (#38, 2026-10-01) is acknowledged and has no accepted time.
- `docs/collaboration-interface.md` line 58 (`bridge_agents`) does not say when `lastSeen`/`lastActivity` change, what
  `running` does and does not promise, or when `waiting` and `owesReplies` clear; a full stop is missing before
  "Since interface 2.4".

## Assumptions (accepted by the user 2026-10-17)

1. **N = 5 minutes from `accepted`.** It catches all nine slow Codex messages and none of the six slow-but-normal ones;
   nothing fell between three and five minutes. Same as D193. With the 30-second check the notice comes at most about
   5.5 minutes after the ping was accepted. Ten minutes would miss #1394, #3978 and #3994.
2. **The condition**: the recipient's wake target is Codex; its wake job for the message is still `accepted` (not
   `read`, not `acknowledged`); the message is direct, has no `read_at`, no acknowledgement and is not expired; its
   accepted time is known and at least five minutes old. Each message counts once.
3. **No false alarm for a slow task**: a turn woken by a ping reads the mailbox first, which sets `read_at` and moves
   the job to `read`. A task that read and then works for an hour is never flagged; only one that did not even read is.
   Presence is not consulted: it can only say `running`.
4. **Who is told**:
   - (a) the user, by a desktop notice as D67: once per message, the same switches (`notify.off`,
     `AGENT_RELAY_NOTIFY=off`) and preview rule (D89). Meaning: Codex confirmed a new turn but has not read message #N in
     five minutes; its mailbox connection may be closed (common after an upgrade or after bridge processes were ended);
     quit ChatGPT completely (⌘Q), open it again and open that task.
   - (b) the sender, in `bridge_outbox` and `bridge_wake_status`: the message's `wake` gains an optional marker and its
     detail says the same.
   - (c) the sender, by one automated message from `bridge`, once per message, as the failure notices are, because a
     sender waiting for a reply does not necessarily look at its outbox.
5. **The interface only grows**: no new delivery state and no new wake state; `accepted` stays terminal. Only optional
   fields and wording. `presence` is unchanged (still `running` as the app says). The recipient's `waiting` in
   `bridge_agents` carries the same marker so the patrol view sees it.
6. **Claude recipients are not handled**: all 1469 were read within a minute, and when a Claude session's bridge goes
   away its process is gone too, which D193 already reports.
7. **Not built**: using D196's "ChatGPT started before the newest upgrade" to shorten N or change the wording (it cannot
   see a bridge ended without an upgrade); re-pinging automatically (`bridge_register` already reports unread
   messages); reading Codex private state.
8. **Release**: bridge change, 0.8.2, `upgrade --confirm`. Interface 2.4 → 2.5; mailbox schema 7 unchanged.
9. Module id `accepted-unread-notice`; depends on codex-gated-wake, delivery-state-machine, claude-offline-notice,
   codex-not-loaded, agents-view-polish.
10. **Interface document, wording only, no behaviour change** (`docs/collaboration-interface.md`, the `bridge_agents`
    row):
    - `lastSeen` changes only when that identity calls a mailbox tool (register, send, inbox, ack, wait …);
      `lastActivity` is the latest of `lastSeen`, its last sent message and its last acknowledgement. Neither is a
      heartbeat; neither says whether the connection works.
    - `presence.state` `running`: for Claude, the session's process is alive, idle included; for Codex, the ChatGPT app
      has the task loaded. Neither means the mailbox (MCP) connection works; after "Transport closed" it can still read
      `running`. The marker of this module is the signal for that case.
    - `waiting` clears when the recipient acknowledges (or the message fails or expires); `owesReplies` clears when the
      recipient answers with `replyTo`, the request is closed through `alsoAnswers`, or the sender withdraws it with
      `withdraws` (or it fails or expires, or the recipient is retired). An acknowledgement does not clear
      `owesReplies` (D202).
    - The missing full stop before "Since interface 2.4".
    Counted in interface 2.5 together with the new marker; the CHANGELOG lists the two separately ("new marker",
    "clarified meaning").

## Decisions

- **D228 a Codex ping accepted five minutes ago whose message is still unread and unacknowledged is a doubtful
  delivery.** Assumptions 1–3, 6. Decided when read, from the stored times (`delivery_changed_at`, `read_at`,
  acknowledgements, the job state); nothing new is stored. Only jobs accepted in the last 24 hours count, so the
  release does not raise notices about old messages. Constant `ACCEPTED_UNREAD_AFTER_MS = 5 * 60_000` next to the other
  thresholds in `notify.ts`.
- **D229 the user is told once per message.** Assumption 4(a). Raised from the 30-second check (`checkApprovals`'s
  tick) by whichever bridge runs it; the `notified/` mark `accepted-unread-<message id>` keeps it to one notice across
  bridges. Notice kind `accepted-unread`, no click action (nothing confirms where the task is; as D188 for a Codex
  target that did not answer on its own).
- **D230 the sender sees it, and is told once.** Assumption 4(b), 4(c), 5.
  - `bridge_outbox` and `bridge_wake_status`: `wake.doubt: {reason: "accepted-unread", since}` (`since` the ISO
    accepted time), and the detail gains the plain sentence. Absent when the condition does not hold.
  - `bridge_agents`: `waiting.doubtfulIds` (the waiting ids that are doubtful, oldest first, at most 20); absent when
    none.
  - One message from `bridge` to the sender, body naming the message id, the recipient and what the user was told, plus
    "This is an automated bridge notice. Do not reply to it."; in the message's thread when it has one; idempotency key
    `accepted-unread:<message id>`, so several bridges send it once. Skipped when the sender is `bridge`, the recipient
    itself, unknown or retired, as `sweepDeliveryFailures`.
- **D231 the `bridge_agents` fields an upper layer relies on are defined in the interface document.** Assumption 10.

## Requirements

1. Red first, `bridge/test/` (fake clock, notice log `AGENT_RELAY_NOTIFY_LOG`):
   - a Codex job `accepted` 4 min 59 s ago with the message unread → nothing; at 5 min → one notice naming the message,
     sender and recipient; further checks and a second bridge add none;
   - the message read (`read_at`, job `read`) or acknowledged before five minutes → nothing, ever;
   - a Claude target, a job in any other state, an expired message, a job accepted more than 24 hours ago, or one with
     no accepted time → nothing;
   - `notify.off` and `AGENT_RELAY_NOTIFY=off` silence the desktop notice but not the outbox marker or the sender
     message; the preview follows D89.
2. Red first, sender: exactly one `bridge` message per doubtful message, in its thread, with the idempotency key, also
   with two bridges checking; none when the sender is `bridge`, the recipient, unknown or retired.
3. Red first, views: `bridge_outbox` and `bridge_wake_status` carry `wake.doubt` and the sentence only while the
   condition holds and drop it once the message is read or acknowledged; `bridge_agents` `waiting.doubtfulIds` likewise;
   every other field unchanged.
4. Docs: `docs/collaboration-interface.md` (the new marker in `bridge_outbox`, `bridge_wake_status` and `bridge_agents`,
   and the assumption 10 wording), `docs/BACKGROUND-WAKE.md`, the `collab` skill (what a doubtful delivery means and what
   to tell the user), CHANGELOG `[Unreleased]`, `interface.json` 2.5, `UPSTREAM.md` and manifest (D24).
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Always: interface changes are additions only; `accepted` stays terminal; the check is read only on the mailbox except
  the `bridge` message and the `notified/` mark.
- Ask first: every test notice on this Mac; any change to the five-minute threshold or the 24-hour window.
- Never: end, restart or reconnect a Codex task or the ChatGPT app from the bridge; read Codex private state; re-ping a
  message automatically; change Claude recipients' handling.

## Acceptance (coordinator, after 0.8.2)

- On the real host, with a test Codex task whose bridge process was ended while the ChatGPT app keeps running: a message
  to it becomes `accepted`, and about five minutes later the user gets one notice, the sender one `bridge` message, and
  `bridge_outbox`/`bridge_agents` show the marker; after the user restarts ChatGPT and the task reads the message, the
  marker is gone and nothing more is sent.
- A normal Codex task that reads within a minute shows no marker.

## Open questions

- None for this module. Shortening N with the D196 upgrade signal stays out (assumption 7).
