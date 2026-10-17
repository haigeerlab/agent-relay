# Todo: accepted-unread-notice

- [x] Task 1: the doubtful-delivery query (D228) — red first (`ACCEPTED_UNREAD_AFTER_MS` missing), then `wakes.acceptedUnread(now, agent?)`: job `accepted` with its own target Codex, message accepted, unread, unacknowledged, accepted 5 min to 24 h ago; tests cover 4 min 59 s, read, acknowledged, older than a day, no accepted time, another job state, and rebinding in both directions
- [x] Task 2: the desktop notice (D229) — red first (no `checkAcceptedUnread`), then notice kind `accepted-unread` (title names the recipient, subtitle `Codex · #N from <sender>` plus the D89 preview, body both causes), mark `accepted-unread-<id>`, run on the 30-second tick separately from `checkApprovals`; a second tick and a second bridge add none; both switches silence the banner only
- [x] Task 3: the sender message (D230, part 1) — red first, then `noticeAcceptedUnread` in `notices.ts`: one `bridge` message in the original thread, key `accepted-unread:<id>`, once across two bridges and three ticks, sent with notices off; none to `bridge`, the recipient itself or a retired sender
- [x] Task 4: the views (D230, part 2) — red first through the MCP server: a new Codex bridge process reads before registering again (`readRecorded: false`), the message stays doubtful; then `wake.doubt` and the added detail in `bridge_outbox` and `bridge_wake_status`, `waiting.doubtfulIds` in `bridge_agents`, computed on read; registering again and reading once more clears all three
- [x] Checkpoint (report): bridge green — `npm run typecheck` clean, `npm test` 265 pass
- [ ] Task 5: interface 2.5, docs and bookkeeping (D231)
- [ ] Checkpoint (report): local validation
- [ ] Task 6: PR and CI
- [ ] Checkpoint (gate): module review
