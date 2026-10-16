# Todo: ack-records-read

- [x] Task 1: ack records read — red first (`read_at` stayed empty after an ack), then `BridgeStore.ack` sets `read_at` with `COALESCE` for each newly acknowledged direct message inside the same transaction; tests: ack sets it, an earlier time is kept, another agent's ack, a repeated ack and a broadcast change nothing
- [x] Task 2: bookkeeping — `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]`
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH after all three modules (47 files, 803 tests each; bridge `npm run check` 203 ok)
- [x] Checkpoint (gate): module review — the round-2 coordinator reviewed #107 (four additions, all made) and #108 (one misplaced comment, fixed in f1213ff); the user merged #107 (e9e2eed) and #108 (f7707f5)
