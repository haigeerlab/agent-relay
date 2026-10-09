# Plan: delegation-hygiene

Based on [`spec/delegation-hygiene.md`](../../spec/delegation-hygiene.md) (accepted by the user on 2026-10-09:
assumptions 1–7, D166–D170). Branch `claude/delegation-hygiene` from main b634c16. Last module of the round-2 batch
(0.6.0, interface 2.0). Spec Guard 0.56.0 already accepts `>=1.0,<3.0`.

## Task List

### Task 1: review scope in the envelope (D166)
Red first: `create --scope` validation (inside the project, exists, safe-review only → `scope-review-only` otherwise);
the control envelope names the scope and asks for "Files read:".

### Task 2: the Claude hard limit (D167)
Red first: `hooks/delegation_scope_hook.py` on fixture events (inside allowed; outside, symlink escaping, pathless
Grep/Glob outside the scope and malformed input denied); a scoped Claude launch carries exactly one `--settings` with
the hook; an unscoped launch argv is unchanged.

### Task 3: friendly name as alias (D168)
Red first: routing resolves a friendly name to the one active delegation's mailbox name, asks on several, leaves exact
mailbox names alone.

### Task 4: prune stuck records (D169)
Red first: `prune` preview lists only stale `creating`/`unknown` records without a live host; `--confirm` cancels
exactly those (reason `pruned-stale`); a second run finds none.

### Task 5: interface 2.0 and docs (D170)
`interface.json` "2.0" only (status contract pinned by `test_packaging`); `relay_status.py` history note; interface
document version and Spec Guard range; README, skills, CHANGELOG (2.0 breaking list).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14.

### Task 6: PR and CI
Push and open the PR; the four CI jobs green.

### Checkpoint (gate): module review
The user reviews and merges; then the 0.6.0 release and the coordinator's real-host acceptance of the whole batch.
