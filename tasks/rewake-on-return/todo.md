# Todo: rewake-on-return

- [x] Task 1: re-arm — red first (`parseProcStart` did not exist), then `WakeQueue.rearm`, `countExpired`, `parseProcStart` (UTC), `sentAt` on jobs and the old-message line in `wakeNotice`; `bridge_register` re-arms and says how many in `next`; the dispatcher re-arms for a live Claude session started after the expiry (`claudeSessions` injectable). Tests: what is and is not re-armed, target and counters, `notified_at` kept, cut-off by process start, +08:00 case, order by job id, once per start, no second offline notice, register via a real stdio session
- [x] Task 2: bookkeeping — `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]`, `docs/BACKGROUND-WAKE.md`
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH after all three modules (47 files, 803 tests each; bridge `npm run check` 203 ok)
- [ ] Checkpoint (gate): module review
