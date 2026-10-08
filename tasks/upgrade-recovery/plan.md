# Plan: upgrade-recovery

Based on [`spec/upgrade-recovery.md`](../../spec/upgrade-recovery.md) (accepted by the user on 2026-10-08: assumptions
1–8, D104–D110). Branch `claude/upgrade-recovery` from main 64c6739. Red → green, one commit per task. Last module of
0.5.0; the release follows. The round-2 coordinator reviews the PR before the user merges.

All code is in `hooks/native_collaboration_runtime.py`; tests in `hooks/test_native_collaboration_runtime.py` (or a new
`test_runtime_recovery.py`). After any change under `bridge/` regenerate `UPSTREAM.sha256` (none expected here). Record
validate only after its output says `validate: pass`.

## Task List

### Task 1: journal, status `interrupted`, `recover --confirm` (D104, D105, D109)
Red first: a runtime directory set up as each upgrade step would leave it after a kill (journal with `step`, mailbox in
stage / runtime renamed / no `runtime/`) → `status` is `interrupted` with the next step; `install`, `upgrade`,
`uninstall` refuse; `recover --confirm` restores the pre-swap layout, row counts equal, the build kept as
`.runtime-upgrade-failed-*`, journal gone; `recover` without a journal or with a running bridge refuses. Then the
journal helpers (atomic write, 0600), `status`, the refusals, `recover_runtime`, the CLI command.

### Task 2: guarded, journalled upgrade and reinstall with unique stages (D104, D106, D107)
Red first: a forced exception at each upgrade step (after the mailbox move, after `runtime` → previous, at the final
rename, at verification) and each reinstall step ends in the pre-swap layout with no journal; a pre-existing directory
named like the old reinstall stage survives a failed reinstall. Then `upgrade_runtime` and `_reinstall_around_history`
write the journal step by step and roll back through the Task 1 steps on any exception; stage names per D107.

### Checkpoint (report): validate on one Python

### Task 3: `rollback --confirm` (D108)
Red first: rollback swaps to the newest `runtime.previous-*` with mailbox and data, counts equal, current build kept as
`runtime.rolled-back-*`, mailbox backed up first; refuses without a previous, with a running bridge, with a journal; a
kill mid-rollback is recovered by `recover`. The upgrade result's `rollback` text names the command.

### Task 4: doctor and docs (D109, D110)
Red first: doctor's runtime check fails with the `recover` next step when a journal exists. Then README upgrade
paragraph, collaboration-ops skill, interface §2.3 runtime row, CHANGELOG `[Unreleased]`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 5: live check
`mktemp -d` HOME: v0.4.0 runtime → `upgrade --confirm` → `rollback --confirm` (status shows the v0.4.0 bridge, counts
equal) → `upgrade --confirm` again → an upgrade interrupted on purpose (process killed after the runtime rename) →
`status` interrupted → `recover --confirm` → ready, counts equal. Temporary HOME to the Trash.

### Checkpoint (gate): module review
Then push and PR with the user's approval; the round-2 coordinator reviews; the user merges after CI is green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Recovery moves the mailbox to the wrong place | High | Journal `step` per move; tests for every step; row counts checked before the journal is removed |
| A journal left by a crash blocks normal use | Medium | `status` and doctor name `recover --confirm`; recover is idempotent |
| Rollback onto a runtime whose plugin hooks read only schema ≤ 4 | Medium | Result repeats the caveat; README says to roll the plugin back too |
