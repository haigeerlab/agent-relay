# Plan: delegation-sidecar-race

Based on [`spec/delegation-sidecar-race.md`](../../spec/delegation-sidecar-race.md) (accepted by the user on 2026-10-08:
assumptions 1–5, D71). Branch `claude/dreamy-lumiere-9a03af` from main 55c6bad. Red → green, one commit per task.

The fix and its test were written before the spec, while finding the cause; Task 1 records that red → green run and
adds what is still missing.

## Task List

### Task 1: A vanished sidecar is absent, not an error (D71)
Test in `test_session_delegation.py` `PrivateStoreTests` first: a real 0600 `-journal` is deleted just before `lstat()`
reads it; `count_delegations` returns 0. Red on main with `FileNotFoundError`. Then `_check_sidecars`: `lstat()`
directly, `continue` on `FileNotFoundError`; unsafe sidecars still rejected. CHANGELOG `[Unreleased]` entry.
**Files:** `hooks/session_delegation.py`, `hooks/test_session_delegation.py`, `CHANGELOG.md`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + 300 runs of the concurrent test on 3.14
Bridge `npm run check` only if `node_modules` is present (Python-only change).

No live check: the store is local and the deterministic test reproduces the interleaving.

### Checkpoint (gate): module review
