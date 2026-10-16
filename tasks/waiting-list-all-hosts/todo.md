# Todo: waiting-list-all-hosts

- [x] Task 1: waiting for every host — red first (the store had only `codexWaiting`), then `BridgeStore.waiting()` for every non-retired agent with `oldestAt`; `bridge_agents` uses it and its description says every host; `docs/collaboration-interface.md` states the add-only promise; the `collab` skill reports waiting for any host with presence
- [x] Task 2: bookkeeping — `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]`
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH after all three modules (47 files, 803 tests each; bridge `npm run check` 203 ok)
- [ ] Checkpoint (gate): module review
