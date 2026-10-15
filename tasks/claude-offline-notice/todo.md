# Todo: claude-offline-notice

- [ ] Task 1: the offline notice for Claude recipients (five minutes, once per offline spell, name/count/earliest time) — red test first
- [ ] Task 2: the sender sees the reason (`wake.pendingReason`, plain detail for a pending Claude job) — red test first
- [ ] Task 3: bookkeeping — `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]`, `docs/BACKGROUND-WAKE.md`
- [ ] Checkpoint (report): local validation — `scripts/validate.sh` on Python 3.9, 3.10, 3.14 with Node 24; bridge `npm run check`
- [ ] Task 4: real check against a scratch mailbox — ask first
- [ ] Task 5: PR and CI
- [ ] Checkpoint (gate): module review — the coordinator reviews; the user merges; then the 0.6.7 release PR
