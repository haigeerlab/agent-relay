# Todo: expiry-notice-reason

- [x] Task 1: one predicate, and the Claude-offline text (notices) — red first (the exports did not exist), then `isClaudeHold` (state `held`, or `refused` with the new `CLAUDE_EXPIRED_RECEIPT` constant in `claude-wake.ts`), `isClaudeOfflineExpiry` and `CLAUDE_OFFLINE_EXPLANATION` in `notices.ts`; with the old regex put back temporarily, both new `delivery.test.ts` cases fail (red for the right reason)
- [x] Task 2: the same predicate in `bridge_wake_status` and the send-time warning — red first (`mcp-integration`: an offline-only list carried the hold `explanation`; `lifecycle`: the warning lacked the not-running sentence, also red against the old `addressing.ts`). Deviation from the plan: the send-time warning must tell an offline expiry from an unreachable one, whose details are identical, so `health()` rows now carry `pendingReason` (one more column in its query); no other query changed
- [x] Checkpoint (report): bridge green — `npm run check` (typecheck, build, 232 tests pass); no `/expired|held/` regex left in `src`
- [x] Task 3: bookkeeping — `UPSTREAM.md` row and manifest (D24), `bridge/CHANGELOG.md` 0.7.2 section, CHANGELOG `[Unreleased]`, `bridge/INSTRUCTIONS.md` (the "held or expired" sentence) and `docs/BACKGROUND-WAKE.md` ("Why Claude pings expire" now opens with the offline case)
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH (47 files, 835 tests each; bridge `npm run check` 232 ok)
- [ ] Task 4: PR and CI
- [ ] Checkpoint (gate): module review
