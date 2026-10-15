# Spec: claude-offline-notice-fixes

## Objective

Only module of 0.6.8 (bridge). The round-2 coordinator's post-hoc review of 0.6.7 (`claude-offline-notice`, D193) found
three small defects, accepted as real after a read-only check; the user decided on 2026-10-15 to fix all three in 0.6.8
("做，三处一起放进 0.6.8"; "确认，七条假设通过"). 0.6.7 stays acceptable and is not rolled back.

Readers: the user; the round-2 coordinator (reviews, re-checks after release).

## What exists today (main 0a7e870, v0.6.7)

1. **Running but unreachable is reported as offline.** `bridge/src/claude-wake.ts` returns `pending` without a reason in
   two cases: several live sessions match the target (`"Claude session has no unique live local inbox"`), and the local
   inbox cannot be reached or fails its ownership checks (`"Claude local inbox unavailable or failed ownership checks"`).
   `wake-queue.ts` `finish()` stores a missing reason as `offline` (`result.reason ?? "offline"`), and
   `wake-dispatcher.ts` `noticeClaudeOffline` accepts a missing reason as offline (`(result.reason ?? "offline")`). So a
   session that is running can get the "is not running" notice, and `bridge_outbox` shows `pendingReason: "offline"`.
2. **A misplaced comment.** `WakeQueue.waiting()` was inserted between `health()`'s doc comment
   (`/** Most recent ping outcomes for one recipient, newest first. */`) and `health()` itself.
3. **Retries drop "a notice was attempted".** Only the attempt that sends the notice appends `NOTIFIED_TEXT` to the wake
   detail; every later retry of the same job overwrites the detail without it, and later jobs of the same offline spell
   never carry it. The sender then cannot tell that the user was already told. The Codex path (`noticeUndelivered`,
   D67) has the same gap.

## Assumptions (accepted by the user 2026-10-15)

1. **A new pending reason `unreachable`**, used in the two cases of defect 1: several matching live sessions, and an
   inbox that cannot be reached or fails ownership checks. Each case gets its own plain detail sentence. The outbox
   then shows `pendingReason: "unreachable"`, not `offline`.
2. **Unreachable is not notified.** This module only removes the false notice. Whether a running but unreachable
   session should be told to the user is a separate question for later. The offline notice accepts only an explicit
   `reason: "offline"`.
3. **Retry rules unchanged:** `unreachable` expires like `offline`, one hour after the message (the expiry query already
   treats every reason except `busy` alike); the message stays in the inbox.
4. **Defect 3:** on every later retry, if the notice for this message (Codex) or this offline spell (Claude) was already
   attempted, `NOTIFIED_TEXT` is appended again; no second notice is sent. Both paths.
5. **Defect 2:** the comment moves back above `health()`; no behaviour change.
6. **Release:** bridge change, 0.6.8, needs `upgrade --confirm`. Interface 2.0, mailbox schema 5, delegation store
   schema 3 unchanged; `pendingReason` gains one possible value.
7. **Review:** the round-2 coordinator reviews the PRs as usual.

## Decisions

- **D194 a Claude session that is running but cannot be reached waits as `unreachable`, never as `offline`; only an
  explicit `offline` result counts toward the offline notice; once a notice was attempted, every later retry keeps
  saying so.** Assumptions 1–5.

## Requirements

1. Red first, `bridge/test/claude-wake.test.ts`: two live sessions matching the target → `pending`, `reason:
   "unreachable"`, the "several sessions" detail; an inbox that cannot be reached (socket missing or refusing) →
   `pending`, `reason: "unreachable"`, the "cannot be reached" detail. The existing offline cases keep `reason:
   "offline"` and `CLAUDE_NOT_RUNNING`.
2. Red first, `bridge/test/notify.test.ts`:
   - a Claude recipient whose wake stays `pending`/`unreachable` for more than five minutes gets no notice;
   - a pending result with no reason gets no Claude offline notice;
   - after the Claude offline notice, the next retry of that job and a later job of the same spell both carry
     `NOTIFIED_TEXT` in their detail, and still only one notice exists;
   - after a Codex notice (offline, held, or busy past ten minutes), the next retry of that message carries
     `NOTIFIED_TEXT`, and still only one notice exists;
   - with notices off nothing is appended.
3. Red first, outbox (`test/delivery-state.test.ts`): a job finished `pending`/`unreachable` shows
   `pendingReason: "unreachable"`.
4. `PendingReason` becomes `"busy" | "offline" | "unreachable"`; the `bridge_outbox` description lists it; the expiry
   text stays as it is ("unreachable for the whole one-hour retry window" already fits).
5. Bridge bookkeeping in the same commit (D24): `UPSTREAM.md`, `python3 -B scripts/bridge-manifest.py`; CHANGELOG
   `[Unreleased]`; `docs/BACKGROUND-WAKE.md` names `unreachable`.
6. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Always: tests first; only the three defects.
- Ask first: every test notice on this Mac; any notice for `unreachable`.
- Never: change detection of offline, the five-minute threshold, the retry windows or any schema.

## Acceptance (coordinator, after 0.6.8)

- `bridge_outbox` for a stopped Claude session still shows `offline` and the notice still comes after five minutes; a
  later retry's detail still says a notice was attempted.
- Code review: the two unreachable cases carry `reason: "unreachable"`; `noticeClaudeOffline` requires an explicit
  `offline`; the comment sits above `health()`.

## Open questions

- Whether a running but unreachable Claude session should be told to the user (assumption 2): not in this module.
