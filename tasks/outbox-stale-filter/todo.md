# Todo: outbox-stale-filter

- [x] Task 1: default stale filter, `includeStale`, `hiddenStale` (D294–D297)
  - Accepted by the owner: new `outbox-stale.test.ts` (owner strengthened the `awaitingReply` case with a real open request); `delivery-state`, `script-access`, `script-cli` tests pass `includeStale` / seed an expired message; manifest updated. Bridge `npm run check` 349 pass. `validate.sh --quick`: first run FAIL with no failure line kept in the tail, second run pass — to re-check in the full run.
- [x] Task 2: interface 2.13, skill and docs (D296, D298)
  - Accepted by the owner: new `test_outbox_stale_docs.py`; interface 2.13 (`interface.json`, `test_packaging.py`, `relay_status.py` history); interface doc `bridge_outbox` and CLI `outbox` rows; collab skill paragraph (D298); CHANGELOG `[Unreleased]`; `UPSTREAM.md` row, manifest rerun. Doc and packaging tests: 17 OK.
- [x] Checkpoint (report): owner acceptance of Tasks 1–2
  - Same-vendor review (`/delegate:review --backend claude-code`, base 9b408ec, with the Spec; delegate 0.12.5): no blocking, 2 suggestions — CLI test did not prove the filter, `includeStale` case checked ids only. Both fixed (CLI asserts `hiddenStale: 1` and no stale id; `includeStale` checks `deliveryState` / `recipient` and field-for-field equality). Diff grep: no real session id or consumer name. The other tests the plan named (`delivery-expiry`, `script-views`, `mcp-integration`) pass unchanged. Full `bash scripts/validate.sh`: pass (53 files, 1105 tests); an earlier full run failed only because two test files were edited mid-run before the manifest was rerun.
- [x] Checkpoint (gate): push and open the PR
  - User approved 「批准，推送开 PR」 (2026-11-26); merge waits for the user's 「合并」 (F3).
