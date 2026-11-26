# Spec: idle-wake-batching

<!-- spec-guard: review approved 0cd72aa2a6dc -->

## Objective

Request from ecosystem-lead (mailbox #23290, 2026-11-26, the user's words 「对，按这个来」). From 11-24 the user's Claude
sessions spent about $1,745 (API-equivalent); 372 turns, about $161, were wakes that did no real work. 220 of them, $89,
were agent-relay mailbox pings, and half of those reached a session that had been idle for over an hour, so its whole
prompt cache had to be written again — the most expensive part.

This module stops pinging an idle Claude session for a message that needs no answer. The ping is held and goes out
together with the next one that has to go out, or as soon as the session is active again, or shortly before the message
would expire. No message is lost, and the sender can see that its ping is held. Scope: assumptions 1–8 confirmed by the
user in the owner session (「假设都对，写 Spec」, 2026-11-26).

Within the boundary draft §2 「唤醒与送达」 (plugin-ecosystem `research/2026-11-26-插件功能盘点/边界草稿/agent-relay.md`).

Readers: the user; the owner session (review, release, acceptance); ecosystem-lead (interface 2.14, release notice).

## What exists today (main 819e2f8, v0.10.1, interface 2.13, schema 8)

- `bridge_send` (`send.ts`, `bridge-store.ts` 525): every direct message whose `wake` is not `false` gets a wake job
  (`wakes.enqueue`). `wake` is optional in the MCP schema, so an omitted `wake` and an explicit `wake: true` reach the store
  the same way; nothing records which it was. The runtime CLI `send` has only `--no-wake` (`cli-logic.ts` 96).
- `WakeDispatcher.drain` (`wake-dispatcher.ts`) claims one job every 2 s (`wakes.claim`) and pings the target at once.
  `CLAIMABLE` (`wake-queue.ts`) keeps one ping in flight per recipient, oldest first: a job waits while an older job for the
  same recipient is `pending` or `sending` (durable-ordering).
- A `pending` job with reason `busy` lives 24 h (`BUSY_WAKE_WINDOW_MS`); any other `pending` job expires after 1 h
  (`OFFLINE_WAKE_WINDOW_MS`). rewake-on-return (D199) pings once more after a Claude session comes back.
- A direct message still `queued` expires at `expires_at` (default 24 h, `BRIDGE_QUEUE_TIMEOUT_MS`, at most 7 days) and
  is then hidden from `bridge_inbox` unless `includeExpired` — "history: never act on it".
- Claude Code's session registry gives each live session `status` (`busy`, `idle`, `waiting`) and `statusUpdatedAt`
  (`claude-wake.ts` 18, `presence.ts` `claudePresence`). The dispatcher already reads it every 30 s (`checkApprovals`).
- Nothing in a Claude session reminds it of unread mail when the user next talks to it: no hook reads the mailbox.

## Assumptions (confirmed by the user, 2026-11-26)

1. Claude recipients only. Codex recipients are unchanged (the cost counted is Claude's, and Codex gives no idle time).
2. "Idle long" = the recipient's Claude session is `idle` in Claude Code's registry and its `statusUpdatedAt` is at least the
   threshold ago. Busy, waiting for approval or input, no status time, or registry unreadable: pinged as today. Stopped
   sessions cannot be pinged today either; unchanged.
3. Threshold 60 minutes by default (the prompt cache lasts an hour), `BRIDGE_IDLE_HOLD_MS` configurable, `0` turns it off.
4. A held ping goes out at the first of: (a) the session is active again; (b) a ping for the same recipient goes out as
   today; (c) the message is within 1 hour of its `expires_at`. Expiry rules themselves are unchanged.
5. "The sender asked for a wake" = an explicit `wake: true`. Omitted `wake` may be held. CLI gains `--wake`. `wake: false`
   unchanged.
6. The sender sees it: delivery state stays `queued`; the wake's `pendingReason` gains `idle` with a detail saying the ping
   is held, not sent; `bridge_send` warns too. Interface 2.13 → 2.14.
7. ecosystem-lead's cheaper option — make `wake: false` the default for messages that need no answer — is considered and
   not taken (see Alternatives).
8. Released as 0.11.0 per `RELEASING.md`; ecosystem-lead is told on release. The requirement is entered in the local
   ledger with `spec-guard:ticket` before code changes.

## Decisions

- **D299 — what may be held.** A wake job may be held only when all of these hold: the target is a Claude session
  (`target.app === "claude"`, the channel path included); the message is not `expectsReply`; the sender did not pass an
  explicit `wake: true` (D300); the threshold is above 0; the message has more than `IDLE_HOLD_EXPIRY_MARGIN_MS` (1 h) left
  before `expires_at` (a row with no `expires_at` counts as having time left); and the recipient's session, read from
  Claude Code's registry, is `idle` with `statusUpdatedAt` at least the threshold ago. Anything unknown — registry
  unreadable, session not found, no status time, `busy`, `waiting` — means no hold: the job is pinged exactly as today.
  Broadcasts have no wake job and are untouched.
- **D300 — explicit wake recorded.** `wake_jobs` gains `explicit_wake INTEGER NOT NULL DEFAULT 1`. A 0.11 bridge writes
  0 for an omitted `wake` and 1 for an explicit `wake: true` (`bridge_send`, CLI `send --wake`); 2 marks a released job
  (D303). Only 0 can be held, so rows from before the upgrade and rows a 0.10.x bridge inserts (it leaves the column out)
  are never held. Schema 8 → 9 by `addColumn`. `wake: false` still creates no job.
- **D301 — where the decision is made.** In `WakeDispatcher.drain`, after `claim` and before `dispatch`, using one registry
  read. A held job is finished as `state: "pending"`, `pending_reason: "idle"`, `retry_at` far in the future (so neither this
  nor an older bridge claims it), with detail `Held, not sent: <agent>'s Claude session has been idle for N min; the ping
  goes out with its next wake, when the session is active again, or an hour before the message expires.` The message's
  delivery state stays `queued`.
- **D302 — a held job does not block.** `CLAIMABLE`'s "older job pending or sending" test leaves out `pending` jobs with
  reason `idle`, so a later ping for the same recipient is not stuck behind a held one. The 1 h pending window does not
  apply to reason `idle`: a held job ends only by release (D303), by its message expiring (existing `expireDue`, which
  cancels it), or by acknowledgement.
- **D303 — release.** Releasing sets `pending_reason` to NULL, `retry_at` to now and the detail to `Released: <why>`; the job
  is then an ordinary pending ping, claimed in id order. Release happens:
  - (a) every 30 s with `checkApprovals`, from the same registry read: for each recipient with held jobs whose session is
    no longer idle past the threshold (it became `busy` or `waiting`, its `statusUpdatedAt` is newer, or it stopped), all
    its held jobs are released. A stopped session's jobs then follow the existing offline path (pending `offline`, notice,
    rewake-on-return);
  - (b) when the dispatcher is about to send a ping that is not held for a recipient, all that recipient's held jobs are
    released in the same transaction, before the send. The session wakes once and reads its whole inbox; pings for
    messages it has read by then are skipped as today (durable-ordering);
  - (c) in the same 30 s check, any held job whose message is within `IDLE_HOLD_EXPIRY_MARGIN_MS` of `expires_at` is
    released with all other held jobs for that recipient;
  - (d) on start, a bridge whose `BRIDGE_IDLE_HOLD_MS` is `0` releases every held job.
  A released job is never held again.
- **D304 — threshold setting.** `BRIDGE_IDLE_HOLD_MS`, read like `BRIDGE_QUEUE_TIMEOUT_MS`: a whole number of ms; `0` turns
  holding off; any other value outside 60 000 ms … 24 h, or not a number, falls back to the default 3 600 000.
- **D305 — what the sender sees.** `bridge_outbox`, `bridge_wake_status` and the CLI views show the held wake with
  `pendingReason: "idle"` and the D301 detail. `bridge_send`, when the same D299 check run at send time says the
  recipient is idle past the threshold, adds the warning `"<agent>" has been idle for N min; this message needs no reply,
  so its ping is held and goes out with its next wake (see bridge_outbox).` The send itself is unchanged; the dispatcher's
  check is the one that counts. `bridge_agents` `waiting` still counts held messages (they are unhandled).
- **D306 — notices unchanged.** A held ping sends no desktop notice and no `bridge` notice to the sender (holding is not a
  failure). The offline, approval, accepted-unread and Claude-hold notices keep their rules; they apply to a held job only
  once it is released.
- **D307 — runtime CLI.** `agent-relay send` gains `--wake` (explicit wake, D300); `--wake` with `--no-wake` is refused.
  The CLI's single delivery attempt after a send goes through the same dispatcher, so D299 applies to it.
- **D308 — skill text.** The collab and session-routing skills say: a message that needs an answer is sent with
  `expectsReply: true`; pass `wake: true` only when an idle recipient must still be woken now (for example the user is
  waiting on it); notices go without either. When the user asks why a message was not delivered and the wake says
  `idle`, tell them it is held until the recipient's next wake, not lost.

## Alternatives considered

- **Default `wake: false` for messages without `expectsReply`** (ecosystem-lead's "only change a default"). Smallest change,
  but it also stops pinging a recipient that is active and has a warm cache, where a ping is cheap and useful, and nothing
  makes a session look at its mailbox later, so such notices would mostly go unread. Not taken. ecosystem-lead's own use
  of `wake: false` for pure notices stays possible and unchanged.
- **Hold by the mailbox's own `lastSeen`** instead of Claude Code's status: `lastSeen` moves only on mailbox calls, so a
  session busy with other work would look idle. Not taken.
- **Hold Codex pings too**: no idle time is available from the ChatGPT app, and the cost counted was Claude's. Not now.

## Requirements

1. `wake_jobs.explicit_wake` column, schema 9 migration, set from `bridge_send` / CLI (`SendInput` keeps whether `wake`
   was `true`, omitted, or `false`).
2. `PendingReason` gains `"idle"`; `CLAIMABLE` and the pending-expiry SQL treat it as D302 says; release helpers in
   `WakeQueue` (`holdIdle`, `releaseHeld(agent, why)`, `heldAgents()`, held-near-expiry query).
3. Dispatcher: D299 check before dispatch with injectable `claudeSessions` and clock; D303 (a)–(d); `BRIDGE_IDLE_HOLD_MS`
   (D304).
4. `bridge_send` warning (D305); `--wake` in the CLI parser and usage text (D307).
5. Tool descriptions: `bridge_send`'s `wake` says an omitted `wake` may be held for an idle Claude recipient when the
   message needs no reply, and `true` always pings; `bridge_outbox` / `bridge_wake_status` mention `pendingReason: idle`.
6. Skills (D308), in Chinese like the rest of each skill.
7. `interface.json` → `2.14`; `docs/collaboration-interface.md`: rows for `bridge_send` (`wake` semantics, warning),
   `bridge_outbox` / `bridge_wake_status` (`pendingReason: "idle"`, a consumer treats a reason it does not know as
   pending), CLI `send --wake`, schema 9, the header version note; `README.md` 唤醒与送达 section: one paragraph on held
   pings and `BRIDGE_IDLE_HOLD_MS`.
8. `CHANGELOG.md` `[Unreleased]`: the change, schema 8 → 9, "bridge 有改动，要 `upgrade --confirm` 升级运行时".
9. Tests (bridge, node test runner), with an injected registry and clock:
   - held: idle ≥ threshold, no `expectsReply`, omitted `wake` → `pending`/`idle`, nothing dispatched, message `queued`;
   - not held: `expectsReply`; explicit `wake: true`; Codex target; `busy`; `waiting`; idle below threshold; no
     `statusUpdatedAt`; registry unreadable; session not found; threshold `0`; under 1 h to `expires_at`;
   - a held job does not block a later job for the same recipient; the later ping's send releases the held ones first;
   - release on activity (`busy`, newer `statusUpdatedAt`), on stop (then the offline path), near expiry, on start with
     threshold `0`; a released job is not held again;
   - a held job is not expired by the 1 h pending window; it is cancelled when its message expires; acknowledging the
     message closes it;
   - `bridge_send` warning present when idle, absent otherwise; `bridge_outbox` shows `pendingReason: "idle"` and detail;
   - schema 8 → 9 migration keeps existing rows (`explicit_wake` 1, so they are never held);
   - CLI `--wake` parsed, `--wake --no-wake` refused;
   - `BRIDGE_IDLE_HOLD_MS` parsing (D304);
   - `bridge/UPSTREAM.sha256` / `UPSTREAM.md` updated (`scripts/bridge-manifest.py`).
10. `bash scripts/validate.sh` passes (full before merge, `--quick` while working).

## Boundaries

- **Always:** no message lost — every held ping ends released, cancelled by its message's own expiry, or closed by
  acknowledgement; anything unknown about the recipient means ping as today; English code and comments; Chinese commits
  and PR.
- **Ask first:** holding Codex pings; changing the default threshold or the 1 h margin after review; any change to message
  expiry; anything under `.github/`.
- **Never:** changing `wake: false` or `expectsReply` behaviour; a hold that delays an `expectsReply` or explicit-wake
  message; acknowledging or reading messages on a recipient's behalf; a new desktop notice for holds; making `wake: false`
  the default.

## Concurrency boundary

- Exclusive: `plugins/agent-relay/bridge/src/schema.ts`, `plugins/agent-relay/bridge/src/wake-queue.ts`, `plugins/agent-relay/bridge/src/wake-dispatcher.ts`, `plugins/agent-relay/bridge/src/bridge-store.ts`, `plugins/agent-relay/bridge/src/send.ts`, `plugins/agent-relay/bridge/src/server.ts`, `plugins/agent-relay/bridge/src/cli-logic.ts`, `plugins/agent-relay/bridge/src/cli-main.ts`, `plugins/agent-relay/bridge/test/idle-hold.test.ts`, `plugins/agent-relay/bridge/test/schema.test.ts`, `plugins/agent-relay/bridge/test/wake-queue.test.ts`, `plugins/agent-relay/bridge/test/delivery-wake.test.ts`, `plugins/agent-relay/bridge/test/rewake.test.ts`, `plugins/agent-relay/bridge/test/cli.test.ts`, `plugins/agent-relay/bridge/test/script-cli.test.ts`, `plugins/agent-relay/bridge/test/request-closing.test.ts`, `plugins/agent-relay/bridge/UPSTREAM.sha256`, `plugins/agent-relay/bridge/UPSTREAM.md`, `plugins/agent-relay/interface.json`, `plugins/agent-relay/hooks/relay_status.py`, `plugins/agent-relay/hooks/test_packaging.py`, `plugins/agent-relay/hooks/test_idle_hold_docs.py`, `plugins/agent-relay/hooks/native_collaboration_runtime.py`, `plugins/agent-relay/hooks/test_native_collaboration_retire.py`, `plugins/agent-relay/hooks/test_outbox_stale_docs.py`, `plugins/agent-relay/hooks/test_doctor.py`, `plugins/agent-relay/skills/collab/SKILL.md`, `plugins/agent-relay/skills/session-routing/SKILL.md`, `docs/collaboration-interface.md`, `README.md`, `CHANGELOG.md`, `tasks/idle-wake-batching/`
- Shared: 迁移

## Mixed versions

During an upgrade, sessions not yet restarted run the 0.10.x bridge. It never claims a held job (its `retry_at` is in the
future) and does not hold anything itself. It expires a held job after 1 h as an ordinary pending one; the message stays
`queued` and unread, and rewake-on-return or the next ping covers it. Its `CLAIMABLE` still treats an older held job as
blocking, so while only 0.10.x bridges are left to claim for that recipient, a later ping (even `expectsReply`) can wait
up to that hour; restart sessions soon after the upgrade. A 0.10.x insert leaves `explicit_wake` out and gets the
default 1, so a 0.11 bridge never holds it (D300). Once every bridge runs 0.11.0 this no longer applies.

## Acceptance (owner session, after release and upgrade)

1. AC1: a test identity bound to a Claude session left idle for over 60 minutes gets a message without `expectsReply`:
   no ping arrives; `bridge_outbox` of the sender shows `pendingReason: "idle"` and the held detail; `bridge_send` warned.
2. AC2: the same recipient then gets an `expectsReply` message: it is woken once and its inbox shows both messages.
3. AC3: a held message is released when the user starts a turn in that session (ping arrives after the turn).
4. AC4: a message with explicit `wake: true` to an idle session is pinged at once.

## Open questions

None. The default threshold (60 min) and the 1 h expiry margin are the values in the confirmed assumptions.

## Change log

- 2026-11-26, Task 1: `bridge/test/request-closing.test.ts` added to the Concurrency boundary; it pins `SCHEMA_VERSION` (8 → 9), as every schema bump has changed it.
- 2026-11-26, Task 4: `hooks/native_collaboration_runtime.py` (the Python mailbox readers accept schema 9; the rollback caveat names schema 9 and 0.10.x), `hooks/test_native_collaboration_retire.py`, `hooks/test_doctor.py` (its "newer mailbox" case moves from schema 9 to 10) and `hooks/test_outbox_stale_docs.py` (its interface pin becomes "at least 2.13") added to the Concurrency boundary. Every schema bump has changed the readers the same way (b3aeac5 for schema 8); without it `doctor` fails its mailbox check on schema 9.
- 2026-11-26, review (`/delegate:review --backend claude-code`, base 819e2f8): D300's default changed from 0 to 1 so a row
  no 0.11 bridge classified (older rows, 0.10.x inserts of an explicit `wake: true`) is never held; a failed read or write
  while deciding a hold or a release no longer leaves a claimed ping stuck (it is sent as today; the release is best
  effort); Mixed versions names the old bridge's blocking. The README paragraph sits next to the other settings because
  the README has no 唤醒与送达 section (Requirement 7).
