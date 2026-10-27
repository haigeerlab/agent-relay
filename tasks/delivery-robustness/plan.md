# Plan: delivery-robustness

<!-- spec-guard: review approved -->

Based on [`spec/delivery-robustness.md`](../../spec/delivery-robustness.md) (approved by the user on 2026-10-27:
assumptions 1–9, D259–D265; grace 90 s and interface 2.10 accepted with it). Built on branch
`claude/delivery-robustness-094-e0a418`; one PR against `main`. Nothing here touches the main clone, the hosts, the real
mailbox or the runtime on this Mac.

Found while planning (read-only, main 6c8aeb4):
- `claimFailure` (`src/wake-queue.ts:372`) is one `UPDATE … WHERE id = (SELECT … state IN FAILED_STATES …)`; the grace
  is one more condition in that subquery, joined to `messages.delivery_changed_at` and `json_extract(target,'$.app')`.
- A held job never goes back to `pending` (`claim` only takes `pending`); a release arrives as a late receipt through
  `ClaudeWake`'s `onLateReceipt` → `finish` (held → accepted), or a read moves it to `read`. So the grace needs no new
  retry logic.
- The held job's `detail` text is in `src/claude-wake.ts:136`; the explanation constant in `src/notices.ts:16`; the
  send warning in `src/addressing.ts:101`; the `explanation` field in `src/server.ts:355`.
- Tests that pin today's wording: `test/delivery.test.ts:61` (expects `crossSessionInbound`, kept), and the negative
  checks `delivery.test.ts:196`, `delivery-expiry.test.ts:79`, `lifecycle.test.ts:37` (offline cases must not mention
  Bypass; unchanged); `hooks/test_collab_entry.py:56-60` (collab skill keeps `Bypass`, `crossSessionInbound`,
  `BACKGROUND-WAKE.md`).
- `send.ts`: `touch` at :54, `flush` at :75, `forMessage` in the return; `wake-dispatcher.ts` `drain()` at :98.
- `expireDue` is also called inside open transactions (`assertBelowPendingCap`, `claim`, `sweep` inside `deliver`), so
  its read-first shortcut applies only when `!db.isTransaction`.

## Task List

### Task 1: grace for Claude holds (D259; requirement 1)
Red first in `test/delivery.test.ts`: a Claude job finished `held` is not claimed by `claimFailure(now)` while its
message's `delivery_changed_at` is within 90 s, and `sweepDeliveryFailures` sends nothing; at `now + 90 s` it is claimed
once; with `delivery_changed_at` set to NULL it is claimed at once; a Codex `held` is claimed at once; a Claude hold
released by a late `accepted` receipt inside the grace is never claimed. Green: `CLAUDE_HOLD_GRACE_MS = 90_000` and the
condition in `claimFailure`. Verify: new and existing delivery / notice tests pass.

### Task 2: hold wording (D260; requirements 2, 6 in part)
Red first: `explainFailure` for a Claude hold, the notice body, the 3-failures send warning and `bridge_wake_status`'s
`explanation` (MCP integration test if one already covers it, else the store-level helper) say the session has usually
just started, may be in Bypass permissions, and not to resend; the notice no longer says "held for approval".
Green: `CLAUDE_HOLD_EXPLANATION`, the notice outcome line, the held `detail` in `claude-wake.ts`. Docs in the same task:
`INSTRUCTIONS.md:16`, `docs/BACKGROUND-WAKE.md` "Why Claude pings expire", skill `collab` step 2 (keeps the phrases
`test_collab_entry.py` checks).

### Task 3: a send that reports an error stored nothing (D261; requirement 3)
Red first in a new `test/send-after-commit.test.ts`: (a) `sendMessage` with a `flush` that rejects resolves with the
stored id, the busy warning, and one stored message; (b) with a second `DatabaseSync` on the same file holding
`BEGIN IMMEDIATE` (released by a timer after the call, busy timeout shortened through the store's connection for the
test, or the lock held across `touch`) the result is the same; (c) a `WakeDispatcher` whose `claim` or `finish` throws
resolves `flush()`; (d) a refusal before the commit (unknown recipient) still throws and stores nothing. Green:
guard the post-commit steps in `send.ts` (one warning per send), and `drain()`'s claim / notice / finish.

### Task 4: less write locking (D262; requirement 4)
Red first in `test/delivery-expiry.test.ts` / `test/wake-queue.test.ts`: `EXPLAIN QUERY PLAN` of the expiry update
names `idx_messages_delivery` and no `SCAN messages`; with another connection holding the write lock, `claim()` on an
idle mailbox returns null at once (well under the busy timeout) and `expireDue` outside a transaction returns `[]` at
once; with due work it still claims. Green: the rewritten condition; the read-first checks in `expireDue` and `claim`.
Verify: all existing expiry, ordering, rewake and claim tests pass unchanged.

### Task 5: retry guidance (D263; requirement 6 in part)
`bridge_send` description and `INSTRUCTIONS.md` prompt: important messages carry an `idempotencyKey`; after an error,
retry with the same key. Test: the existing tool-description / instructions checks, extended with this phrase where one
pins descriptions (else a small assertion in the MCP integration test).

### Task 6: idempotency retry sweeps first (D264; requirement 5)
Red first in `test/request-closing.test.ts`: send A with key k and `alsoAnswers: [r1]`; request r2 (still `queued`)
passes its `expires_at` with no sweep; the retry with key k and `alsoAnswers: [r1, r2]` returns the stored message with
`{id: r2, reason: "expired"}` in `skipped` instead of a content conflict (today r2 still reads as open, so it counts as
a difference). Green: `this.sweep()` at the start of the key branch when an existing message is found.

### Task 7: interface 2.10 and release notes (D265; requirement 6)
`interface.json` `"2.10"` and the tests that pin it (`test_packaging.py` etc., red first); interface document §1 (0.9.4
implements 2.10) and the `bridge_send` / `bridge_wake_status` rows; README interface number where it appears;
`UPSTREAM.md` rows for changed bridge files; `python3 scripts/bridge-manifest.py`; root CHANGELOG `[Unreleased]` 0.9.4
draft entry and `bridge/CHANGELOG.md`. No version-number change.

### Checkpoint (report): everything green
`npm run check` in `bridge/` and `scripts/validate.sh`; recorded in todo.md, then continue.

### Checkpoint (gate): PR and module review
Open the PR against `main`, report to the owner session with one line and the link. Review and release are other
sessions' work; merging is the user's.

## Risks

- The grace hides a real Bypass hold for 90 s longer; accepted in the Spec.
- `claim`'s read-first check must cover every write step in `claimStep`, or a cleanup (e.g. a lapsed `sending` job)
  would wait until other work appears. Task 4's tests exercise each step through existing tests, which must stay green.
- Swallowing post-commit errors could hide a real bug; the warning names the database's own message when it is not a
  busy error.
