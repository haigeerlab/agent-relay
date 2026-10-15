# Plan: claude-offline-notice-fixes

Based on [`spec/claude-offline-notice-fixes.md`](../../spec/claude-offline-notice-fixes.md) (accepted by the user on
2026-10-15: assumptions 1–7, D194). Branch `claude/offline-fixes-impl` from main after this plan's PR. Only module of
0.6.8; the round-2 coordinator is told every PR number; the release PR waits until the implementation PR is merged.

## Task List

### Task 1: unreachable is not offline
Red first in `test/claude-wake.test.ts` (requirement 1) and `test/delivery-state.test.ts` (requirement 3). Green:
`PendingReason` gains `"unreachable"`; the two cases in `claude-wake.ts` return it with plain details; the
`bridge_outbox` description lists it.

### Task 2: only explicit offline is notified; retries keep NOTIFIED_TEXT
Red first in `test/notify.test.ts` (requirement 2). Green in `wake-dispatcher.ts`: `noticeClaudeOffline` requires
`result.reason === "offline"`; both notice paths append `NOTIFIED_TEXT` when this call notified or `alreadyNotified`
holds for the same key (Codex: the message id; Claude: the spell key). Move `health()`'s doc comment back above it in
`wake-queue.ts`.

### Task 3: bookkeeping
`UPSTREAM.md` row, manifest, CHANGELOG `[Unreleased]` (needs `upgrade --confirm`), `docs/BACKGROUND-WAKE.md`.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 4: PR and CI
Push, open the PR, tell the coordinator; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.8 release PR.
