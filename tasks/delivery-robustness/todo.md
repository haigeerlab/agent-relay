# Todo: delivery-robustness

- [x] Task 1: grace for Claude holds (D259) — 3 tests (the 90 s case red), then the condition in `claimFailure` joined to `delivery_changed_at`
- [x] Task 2: hold wording (D260) — wording test (red), then `CLAUDE_HOLD_EXPLANATION`, `CLAUDE_HELD_DETAIL`, the notice line; INSTRUCTIONS, BACKGROUND-WAKE, bridge and root README, skill `collab`
- [x] Task 3: a send that reports an error stored nothing (D261) — `send-after-commit.test.ts` (5 red: flush/touch/lock/drain), then guards in `send.ts`, `drain()` and the CLI send
- [x] Task 4: less write locking (D262) — EXPLAIN and locked-idle tests (red), a with-work guard test; `DUE_FOR_EXPIRY`, read-first `expireDue` and `claimHasWork`
- [x] Task 5: retry guidance (D263) — description assertion in the MCP integration test (red), then the description and INSTRUCTIONS
- [x] Task 6: idempotency retry sweeps first (D264) — expired-unswept retry test (red: conflict), then a sweep before the key lookup
- [x] Task 7: interface 2.10 and release notes (D265) — `test_packaging` (red), `interface.json`, `relay_status.py`, interface document §1 and rows, README zh/en, CHANGELOG draft (root and bridge), UPSTREAM rows, manifest; README status lines and version numbers left to the release PR
- [x] Checkpoint (report): everything green — `scripts/validate.sh` pass, 48 files, 954 tests (bridge `npm run check` 320); the S47 repro script run against this branch's `dist` returns the stored id with the "Saved as #1" warning instead of `database is locked`, one row stored
- [x] Checkpoint (gate): PR and module review — PR #164 merged by the user before review; the post-merge review (Codex plus the owner session) found no loss or duplicate, items 1–6 fixed below (ledger HFQ8Q03)
- [x] Task 8: idle claim matches claimStep (D266) — two locked-idle tests (red: offline recipient with two queued pings; busy ping older than an hour), then `PENDING_EXPIRED` and `CLAIMABLE` shared by `claimHasWork` and `claimStep`
- [x] Task 9: late receipt retried (D267) — late-receipt-under-lock test (red), then `WakeDispatcher.lateReceipt` with five tries 2 s apart
- [x] Task 10: read or acknowledged hold not announced (D268) — held + read and held + ack test (red), then the condition in `claimFailure`
- [x] Task 11: README hold line and S47 tests — bridge README line; finish-failed-then-unknown test and CLI send-after-commit test (both green: guards existing behaviour)
- [x] Checkpoint (report): everything green — see the PR
- [x] Checkpoint (gate): review-fix PR merged by the user — PR #165 merged as f39dbf3 (2026-10-27)

Release: goes into 0.9.4 (release PR opened 2026-10-27; the bridge version moves from 0.9.3 to 0.9.4 there); the tag, the GitHub Release and the runtime upgrade on this Mac are done by the user, one step at a time.

<!-- spec-guard: external-review declined -->
