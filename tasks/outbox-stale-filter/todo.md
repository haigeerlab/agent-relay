# Todo: outbox-stale-filter

- [x] Task 1: default stale filter, `includeStale`, `hiddenStale` (D294–D297)
  - Accepted by the owner: new `outbox-stale.test.ts` (owner strengthened the `awaitingReply` case with a real open request); `delivery-state`, `script-access`, `script-cli` tests pass `includeStale` / seed an expired message; manifest updated. Bridge `npm run check` 349 pass. `validate.sh --quick`: first run FAIL with no failure line kept in the tail, second run pass — to re-check in the full run.
- [x] Task 2: interface 2.13, skill and docs (D296, D298)
  - Accepted by the owner: new `test_outbox_stale_docs.py`; interface 2.13 (`interface.json`, `test_packaging.py`, `relay_status.py` history); interface doc `bridge_outbox` and CLI `outbox` rows; collab skill paragraph (D298); CHANGELOG `[Unreleased]`; `UPSTREAM.md` row, manifest rerun. Doc and packaging tests: 17 OK.
- [ ] Checkpoint (report): owner acceptance of Tasks 1–2
- [ ] Checkpoint (gate): push and open the PR
