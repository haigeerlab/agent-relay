# Todo: ack-records-read

- [x] Task 1: ack records read — red first (`read_at` stayed empty after an ack), then `BridgeStore.ack` sets `read_at` with `COALESCE` for each newly acknowledged direct message inside the same transaction; tests: ack sets it, an earlier time is kept, another agent's ack, a repeated ack and a broadcast change nothing
- [x] Task 2: bookkeeping — `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]`
- [ ] Checkpoint (report): local validation
- [ ] Checkpoint (gate): module review
