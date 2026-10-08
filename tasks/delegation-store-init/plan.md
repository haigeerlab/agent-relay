# Plan: delegation-store-init

Based on [`spec/delegation-store-init.md`](../../spec/delegation-store-init.md) (accepted by the user on 2026-10-09:
assumptions 1–6, D127–D129). Branch `claude/delegation-store-init` from main 608d55f. Red → green, one commit per task.
The round-2 coordinator reviews the PR; the user merges after every CI check has finished green. No release here.

Code: `hooks/session_delegation.py`; tests: new `hooks/test_delegation_store_init.py`. No bridge change. Record validate
only after its output says `validate: pass`.

## Task List

### Task 1: concurrent first open, empty file, directory race (D127, D128)
Red first: 8 rounds × 4 real processes opening one fresh root behind a start barrier → all succeed; a 0-byte database
→ initialized to version 2; version 0 with another table → still refused; the directory appearing between the check and
`mkdir` → accepted when private, refused when a symlink. Then `_prepare_root` (`FileExistsError` falls through to the
existing-path checks), `_prepare_database` (`O_EXCL` losing the race falls through), `_initialize_if_empty` for every
opener. Existing delegation tests unchanged.

### Task 2: docs (D129)
CHANGELOG `[Unreleased]`; interface doc row if it describes initialization.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Checkpoint (gate): module review
Then push and PR with the user's approval; the round-2 coordinator reviews; the user merges after CI has finished green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A foreign database gets tables added | High | initialize only at version 0 with no tables, inside `BEGIN IMMEDIATE` with the check repeated there |
| The multi-process test is flaky | Medium | start barrier, 8 rounds, generous busy timeout already 5 s |
