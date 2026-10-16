# Plan: ack-records-read

Based on [`spec/ack-records-read.md`](../../spec/ack-records-read.md) (accepted by the user on 2026-10-16). Module 1 of 3 in 0.6.10; the three
modules share one implementation branch `claude/release-0-6-10-impl` from main after this plan's PR, one commit per
module; the round-2 coordinator is told every PR number; the release PR waits until the implementation PR is merged.

## Task List

### Task 1: ack records read — red first, then `BridgeStore.ack` records `read_at` for newly acknowledged direct messages in the same transaction

### Task 2: bookkeeping
`UPSTREAM.md` row, `python3 -B scripts/bridge-manifest.py`, CHANGELOG `[Unreleased]` (needs `upgrade --confirm`).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Checkpoint (gate): module review
One implementation PR for the three modules; CI green; the coordinator reviews; the user merges.
