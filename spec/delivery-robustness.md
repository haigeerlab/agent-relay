# Spec: delivery-robustness

<!-- spec-guard: review approved e575e84167b5 -->

## Objective

Three delivery defects for the **0.9.4** patch, decided by the user in the owner session on 2026-10-27 ("同意排进
0.9.4：S46、S47 加 M04WZ94 第 1 条"). S46 and S47 were reported by a consumer session using 0.9.3 (relayed by
ecosystem-lead, mailbox #11926); the read-only diagnosis is in the owner session's notes. M04WZ94 item 1 was left open by
the review of #161. Ledger items: C0J9734 (S46), 6D8R3V2 (S47), M04WZ94 (item 1 only).

Readers: the user; the owner session (review, release, acceptance).

## What exists today (main 6c8aeb4, v0.9.3)

- **S46.** `claude-wake.ts:136` maps a Claude receipt `held` to wake state `held`; the receipt carries no cause.
  `notices.ts` `CLAUDE_HOLD_EXPLANATION` says the recipient runs in Bypass permissions, and is used by the
  delivery-failure notice (`explainFailure`), the "last 3 pings failed" send warning (`addressing.ts:101-104`) and
  `bridge_wake_status`'s `explanation` (`server.ts:354-355`). `held` is in `FAILED_STATES` (`wake-queue.ts:88`), so
  `claimFailure` takes it at the next housekeeping run (≤ 5 s) with no grace. Claude Code also holds a message while the
  session's permission-mode getter is not wired yet (just started), and releases it a moment later; all 8 held notices in
  the mailbox's history were that case, the recipient read the message seconds later. The message's
  `delivery_changed_at` is set when the hold is recorded (`sending → queued`), and nothing else changes it while held.
- **S47.** `send.ts` stores the message in `deliver()`'s `BEGIN IMMEDIATE` transaction, then calls `store.touch(from)`
  (a write) and `await context.flush()` (`wake-dispatcher.ts` `drain()`: `claim()` and `finish()`, both write
  transactions, not guarded). A `SQLITE_BUSY` there makes the whole `bridge_send` fail although the message is
  committed; a retry without an `idempotencyKey` stores it twice (seen: #11835 / #11838). Every bridge opens a
  `BEGIN IMMEDIATE` in `claim()` every 2 s, and its `expireDue` (`delivery.ts`) filters with
  `COALESCE(delivery_state,'queued')='queued'`, which cannot use `idx_messages_delivery` (`SCAN messages`).
- **M04WZ94 item 1.** The idempotency-key retry branch of `insertMessage` (`bridge-store.ts:432-450`) compares content
  through `closableBy` without sweeping first: an id in the retry's lists that has passed its timeout but was not swept
  yet still reads as open, so the retry is refused as a content conflict instead of listing that id in `skipped`.

## Assumptions (to confirm)

1. **One module, bridge runtime only.** Schema 7 unchanged; no new delivery or wake state; nothing newly refused.
   Releasing it needs `upgrade --confirm`. The version numbers (`plugin.json`, `version.ts`, `package.json`) move in the
   release PR, not here.
2. **Grace for Claude holds: 90 seconds.** A Claude ping in `held` is not a failure until its message has stayed held
   for 90 s (`delivery_changed_at` older than now − 90 s; a NULL `delivery_changed_at` gets no grace). A hold Claude
   releases within that time ends `accepted`/`read` and is never announced. A hold that lasts is announced once, as
   today, at most ~95 s after it started. Codex holds, refusals and expiries are unchanged (no grace).
3. **Hold wording.** Every place that explains a Claude hold (notice, send warning, `bridge_wake_status`
   `explanation`, the held job's `detail`, `INSTRUCTIONS.md`, `docs/BACKGROUND-WAKE.md`, skill `collab`) says: Claude
   held the message by permission-mode parity; usually because the session has just started (released on its own within
   seconds), possibly because it runs in Bypass permissions; do not resend while it is held. The Bypass advice
   (switch mode, approve in a terminal, `crossSessionInbound`) stays as the second case. The notice title stops saying
   "held for approval".
4. **A send that reports an error stored nothing.** After `deliver()` commits, a failure of any later step (`touch`,
   `flush`, building warnings or reading the wake state) no longer fails `bridge_send` or the CLI `send`: the result is
   the stored message as usual (`wake` may be null) plus one warning: "Saved as #id; the mailbox database was busy, so the
   ping is retried in the background. Do not send it again." (the database's own message is named when it is not a busy
   error). `drain()` never rejects: a failed `claim()` is a round with no job; a failed `finish()` leaves the job
   `sending`, which the existing lapse rule turns into `unknown` after 30 s (never replayed).
5. **Less write locking, no new index.** `expireDue`'s condition becomes
   `(delivery_state = 'queued' OR delivery_state IS NULL) AND expires_at IS NOT NULL AND expires_at <= ?`, which uses
   `idx_messages_delivery`. Outside an open transaction `expireDue` first checks with a read whether anything is due and
   opens no write transaction when nothing is. `claim()` first checks with one read query whether any of its steps has
   work (a message to expire, a lapsed `sending` job, a `pending` job that is due, acknowledged, read or past its retry
   window); when none, it returns null without `BEGIN IMMEDIATE`. Behaviour is otherwise the same.
6. **Retry guidance.** `bridge_send`'s tool description and `INSTRUCTIONS.md` say: give important messages an
   `idempotencyKey`; after an error, retry with the same key.
7. **M04WZ94 item 1.** The idempotency-key retry branch sweeps expired messages before it compares, so a newly expired
   id is listed in `skipped` (reason `expired`) and the retry returns the stored message. Item 2 (doctor counts) is out
   of scope.
8. **Interface 2.10 (minor),** as the owner session set: a new `bridge_send` warning, the new hold wording in the notice
   and in `bridge_wake_status`'s `explanation`, and held pings announced only after the grace. Nothing removed, renamed
   or narrowed. `interface.json` `"2.10"`; `docs/collaboration-interface.md` §1 and the `bridge_send` /
   `bridge_wake_status` rows. Spec Guard's range `>= 1.0, < 3.0` holds. I assume the owner session's reply to
   ecosystem-lead (#12018) covered the version; if ecosystem-lead must be asked first, implementation waits.
9. **Public repo.** No consumer project or session names anywhere; "a consumer session".

## Decisions

- **D259 Claude holds get a 90 s grace before they count as failed.** Assumption 2.
- **D260 hold wording: permission-mode parity, usually a just-started session.** Assumption 3 (revises the explanation of
  `expiry-notice-reason` D215 and the notice title; which pings count as a hold is unchanged).
- **D261 after the commit, `bridge_send` does not fail.** Assumption 4.
- **D262 `expireDue` uses the index and claims skip empty write transactions.** Assumption 5.
- **D263 retry with the same `idempotencyKey`.** Assumption 6.
- **D264 an idempotency retry sweeps before comparing.** Assumption 7.
- **D265 interface 2.10.** Assumption 8.

### Review of #164 (2026-10-27, before the release)

The post-merge review found no lost or duplicated message, but three gaps in D259 and D262, a README line and two test
gaps (ledger HFQ8Q03). Fixed in one small PR before the 0.9.4 release; behaviour fixes inside interface 2.10, which is
not released yet, so no version change.

- **D266 the idle check matches what `claimStep` can take.** `claimHasWork` used to say "work" for any due pending ping
  and any ping older than an hour, so two cases took the write lock every 2 s for nothing: an offline recipient with two
  or more queued pings (the second is due but waits behind the backed-off first; up to an hour) and a `busy` ping older
  than an hour but inside its day (up to 23 hours). Both now share `claimStep`'s SQL: `PENDING_EXPIRED` (busy and
  other windows apart) and `CLAIMABLE` (due, no older pending or sending ping for the same recipient, not hosted by
  another live channel process).
- **D267 a late Claude receipt's write is tried again.** A "delivered" receipt after a hold is written by
  `finish()`; when the database was busy the error was swallowed and the job stayed `held`, so the sender got the
  90 s hold notice. `WakeDispatcher.lateReceipt` now tries the write up to five times, 2 s apart (inside the grace),
  and never wakes again. Chosen together with D268, not instead of it: D268 needs a recorded read or acknowledgement,
  which a released session may not make within 90 s; the retry covers that case when the receipt reached this
  process.
- **D268 a Claude hold whose message was read or acknowledged is never announced.** The receipt route lives only in
  the process that sent the ping (a CLI `send`, a Codex MCP process restarted per turn, a closed session), so a release
  can go unrecorded. `claimFailure` skips a Claude `held` job whose message has `read_at` or an acknowledgement. A read
  recorded through `recordRead` already moves the job to `read`; this guards the message-level record as well.
- Also: the bridge README says only a hold lasting more than 90 seconds notifies the sender (it said "either way",
  against D259); tests for S47 (a finish that failed is `unknown` after 30 s and not sent again; CLI `send` failing
  after the commit exits 0 with the warning and stores one row), for D266's two idle cases while another connection
  holds the write lock, for D267, and for D268.

## Requirements

1. Red first (`approval-notice` / `delivery-wake` tests): a Claude `held` job younger than 90 s is not claimed by
   `claimFailure` and sends no notice; older than 90 s (or with no `delivery_changed_at`) it is, once; a Codex `held`
   is claimed at once; a hold released inside the grace sends nothing.
2. Red first: the notice, the send warning and `bridge_wake_status`'s `explanation` carry the new wording (just
   started, Bypass, do not resend) and no longer say the recipient is in Bypass as a fact.
3. Red first (S47): with a second connection holding the write lock after the commit (`BEGIN IMMEDIATE` on another
   `DatabaseSync`, released after the call), `sendMessage` resolves with the stored id and the busy warning, the message
   is stored once; a `flush` that rejects for any reason gives the same; `drain()` resolves when `claim()` or `finish()`
   throws. A failure before the commit still throws and stores nothing.
4. Red first: `EXPLAIN QUERY PLAN` of `expireDue`'s update uses `idx_messages_delivery` (no `SCAN messages`); `claim()`
   with nothing to do opens no write transaction (observable: it returns null while another connection holds the write
   lock, without waiting); the existing expiry and claim tests stay green.
5. Red first (`request-closing` or `idempotency` tests): an idempotency-key retry whose list names a request that expired
   after the first send but was not swept returns the stored message with that id in `skipped` (reason `expired`).
6. Docs: `INSTRUCTIONS.md:16`, `docs/BACKGROUND-WAKE.md` "Why Claude pings expire", skill `collab`, `bridge_send`
   description, `interface.json` 2.10, interface document §1 and rows, `UPSTREAM.md` rows, `scripts/bridge-manifest.py`,
   CHANGELOG (root and `bridge/CHANGELOG.md`) 0.9.4 draft entry.
7. `npm run check` and `scripts/validate.sh` green; CI green.

## Boundaries

- Ask first: anything on this Mac's runtime, hosts or real mailbox (none planned; no test messages to the real mailbox).
- Never: a schema change, a new index, a new state, raising `busy_timeout`, tagging or releasing.

## Acceptance (owner session, after release)

- An idle Claude session the app stopped, woken by a message, produces no hold notice; a session really in Bypass still
  gets one after the grace.
- The repro (write lock held during flush) returns the stored id and the warning instead of `database is locked`.

## Open questions

None, apart from assumption 8's ecosystem-lead question.
