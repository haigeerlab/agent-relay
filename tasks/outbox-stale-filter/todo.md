# Todo: outbox-stale-filter

- [x] Task 1: default stale filter, `includeStale`, `hiddenStale` (D294–D297)
  - Accepted by the owner: new `outbox-stale.test.ts` (owner strengthened the `awaitingReply` case with a real open request); `delivery-state`, `script-access`, `script-cli` tests pass `includeStale` / seed an expired message; manifest updated. Bridge `npm run check` 349 pass. `validate.sh --quick`: first run FAIL with no failure line kept in the tail, second run pass — to re-check in the full run.
- [ ] Task 2: interface 2.13, skill and docs (D296, D298)
- [ ] Checkpoint (report): owner acceptance of Tasks 1–2
- [ ] Checkpoint (gate): push and open the PR
