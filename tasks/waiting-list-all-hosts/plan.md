# Plan: waiting-list-all-hosts

Based on [`spec/waiting-list-all-hosts.md`](../../spec/waiting-list-all-hosts.md) (accepted by the user on 2026-10-16). Module 2 of 3 in 0.6.10; the three
modules share one implementation branch `claude/release-0-6-10-impl` from main after this plan's PR, one commit per
module; the round-2 coordinator is told every PR number; the release PR waits until the implementation PR is merged.

## Task List

### Task 1: waiting for every host — red first, then a store query for all agents with `oldestAt`, `bridge_agents` uses it, description and interface document

### Task 2: bookkeeping
`UPSTREAM.md` row, `python3 -B scripts/bridge-manifest.py`, CHANGELOG `[Unreleased]` (needs `upgrade --confirm`).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Checkpoint (gate): module review
One implementation PR for the three modules; CI green; the coordinator reviews; the user merges.
