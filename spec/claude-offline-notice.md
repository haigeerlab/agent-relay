# Spec: claude-offline-notice

## Objective

Only module of 0.6.7 (bridge). From a problem report relayed on 2026-10-15 by a Codex monitoring session
(mailbox name `spec-guard-monitor`), with the user's consent to hand it over, and the user's decision the same day ("做，按你
的建议，离线五分钟后通知"; "确认，八条假设通过"): when the recipient is a Claude desktop session that has gone idle, messages
wait silently until the user happens to open that session. Nobody is told; a multi-session collaboration just stops.

Readers: the user; the round-2 coordinator (reviews, re-checks after release); the reporting session.

## What exists today (main e934c19, v0.6.6)

- Evidence (read-only, `~/.agent-relay/runtime/mailbox/bridge.sqlite`, 2026-10-13 to 10-15): wake jobs for the Claude
  recipients `project-a-hub` and `project-a-arch-review` stayed `pending` with `pending_reason = offline` for 9 to 53
  minutes (13 to 57 attempts) before they were acknowledged; `notified_at` is empty on every one. The process of
  `project-a-arch-review`'s session (registry entry `entrypoint: claude-desktop`) started at 15:24:49; message #1309,
  sent 15:15:54, was delivered right after. So the Claude desktop app stops an idle session's process, and the bridge
  can deliver only to a live process.
- `bridge/src/claude-wake.ts` returns `pending` without a reason when the session has no unique live local inbox or its
  process stopped; `wake-queue.ts` stores that as `offline`. The job keeps retrying (backoff up to one minute) and
  expires after one hour (`OFFLINE_WAKE_WINDOW_MS`).
- `bridge/src/wake-dispatcher.ts` calls `noticeUndelivered` only when `job.target.app === "codex"` (D67: offline or
  held at once, busy after ten minutes, once per message). Claude targets get no notice; the approval notice (D148)
  covers only a Claude session that is running and waiting for the user.
- At send time `bridge_send` already warns when a bound Claude session is not running (`addressing.ts`), and
  `bridge_agents` shows its presence as `stopped`. Afterwards `bridge_outbox` shows each message's wake as
  `{state, detail}` only; for a stopped Claude session the detail reads "Claude session has no unique live local
  inbox" and nothing says "offline".
- The bridge does not store whether a session is a desktop session: `entrypoint` is read only from the live registry
  entry, which is gone once the process stops.

## Assumptions (accepted by the user 2026-10-15)

1. **Offline** means what the bridge already decides: a Claude wake job is `pending` with reason `offline` (no live
   process to deliver to). Nothing about detection changes; it stops being silent.
2. **Five minutes from the message's creation.** Retries run at least once a minute, so the notice comes at most about
   six minutes after the message was sent.
3. **One notice per session, not per message.** While one Claude recipient is offline with several waiting messages,
   one notice names: the session (its mailbox name, e.g. `project-a-hub`), how many messages wait, and when the
   earliest was sent. Once its messages are delivered, a later offline spell notifies again.
4. **No click action.** The bridge cannot tell a desktop session from a terminal one once the process is gone, so the
   notice has no click action (as the offline Codex notice today).
5. **The existing switches apply:** `AGENT_RELAY_NOTIFY=off` / `notify.off`; nothing new to configure.
6. **The sender sees the reason:** each `bridge_outbox` entry's `wake` gains `pendingReason` (`offline` or `busy`)
   while the job is pending, and a pending Claude job's detail says in plain words that the session is not running
   (the desktop app may stop idle sessions) and that the message is delivered once that session is opened.
7. **Not built:** waking a stopped desktop session from outside. The bridge cannot call the desktop app's in-app tools
   (`send_message` is offered only to sessions inside the app); relaying through a running Claude session is
   untested. Left as an open question.
8. **Release:** bridge change, 0.6.7, needs `upgrade --confirm`. Interface 2.0, mailbox schema 5, delegation store
   schema 3 unchanged (the outbox gains an optional field).

## Decisions

- **D193 a Claude recipient offline for five minutes is told to the user once per offline spell; the sender sees why
  its message waits.** Assumptions 1–7.

## Requirements

1. Red first, `bridge/test/notify.test.ts` (with the notice log, `AGENT_RELAY_NOTIFY_LOG`):
   - a Claude recipient whose wake stays `pending`/`offline`: no notice before five minutes; one notice after, naming
     the agent, the number of waiting messages and the earliest one's time; further retries and further messages to the
     same recipient in the same spell add no notice;
   - after its messages are delivered (acknowledged or read), a new offline spell notifies again;
   - a delivered message, a held message (approval path), a `busy` result and a Codex recipient are unchanged;
   - `notify.off` and `AGENT_RELAY_NOTIFY=off` silence it; no click arguments; no message body in the notice;
   - the wake detail records that a notice was attempted (`NOTIFIED_TEXT`), as for Codex.
2. Red first, outbox: a pending job shows `pendingReason`; a pending Claude job's detail is the plain sentence; other
   states carry no `pendingReason`.
3. Bridge bookkeeping in the same commit (D24): `UPSTREAM.md`, `python3 -B scripts/bridge-manifest.py`; CHANGELOG
   `[Unreleased]`; `docs/BACKGROUND-WAKE.md` says Claude offline notices exist.
4. Real check on this Mac, asked first: a test recipient whose wake target is a Claude session with no live process;
   after five minutes one notice is shown (read from the user or the notice log); the outbox shows `offline`.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Ask first: every test notice on this Mac; any change to the five-minute threshold.
- Never: try to wake, start or resume a Claude session from the bridge; read the desktop app's own state; put a message
  body in this notice.

## Acceptance (coordinator, after 0.6.7)

- With a real idle Claude desktop session whose process has stopped: a message to it produces one notice after about
  five minutes with the right name, count and time, and `bridge_outbox` shows `pendingReason: "offline"`; opening the
  session delivers the message; a later spell notifies again.

## Open questions

- Waking a stopped desktop session from outside (assumption 7): not in this module.
