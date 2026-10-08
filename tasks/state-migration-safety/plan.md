# Plan: state-migration-safety

Based on [`spec/state-migration-safety.md`](../../spec/state-migration-safety.md) (accepted by the user on
2026-10-08: assumptions 1–10, D116–D121). Branch `claude/state-migration-safety` from main bf72a2d. Red → green, one
commit per task. The round-2 coordinator reviews the PR before the user merges. No release in this module.

All code is in `hooks/state_migration.py` (journal writer reused from `native_collaboration_runtime.py`); tests in
`hooks/test_state_migration.py` and a new `hooks/test_state_migration_safety.py`. No bridge change. Record validate only
after its output says `validate: pass`.

## Task List

### Task 1: lock and agent-relay's own bridges (D116, D117)
Red first: a `migrate` while the test holds the lock → blocked "another state migration is running", target tree
unchanged; an injected agent-relay bridge count → `detect` blocker and `target_servers`, `migrate` blocked, nothing
written. Then the lock helper around `migrate` (and later `recover`), `target_count` in `inspect`/`migrate`, CLI
unchanged.

### Task 2: staged, journalled, all-or-nothing migration (D118, D119)
Red first: a failure injected at each journalled step (mailbox/data/delegation × retiring/placing, verifying) and a
count mismatch → `rolled-back`, target tree byte-identical, no journal, failed stage kept, old tree unchanged; a
successful migration gives the same target content and backup as before. Rewrite the old mismatch test to the new
expectation. Then the stage, journal and put-back in `migrate`.

### Checkpoint (report): validate on one Python

### Task 3: interrupted and recover (D120)
Red first: journal left at each step with the layout that step leaves (no rollback) → `detect` `interrupted`,
`migrate` refuses, `recover --confirm` restores the pre-migration tree, journal gone; `recover` without a journal, with
a running bridge, without `--confirm` refuses; CLI exit codes. Then `inspect` journal check, `recover`, CLI.

### Task 4: docs (D121)
Interface doc §13 rows, README migration commands, collaboration-ops skill, CHANGELOG `[Unreleased]`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 5: live check
Temporary HOME: Spec Guard-era layout with rows; runtime from this branch; `migrate --confirm` → migrated, counts
equal, old tree unchanged. Second layout: a child process `os._exit`s right after the `placing` journal write of
`mailbox` → `detect` interrupted, `recover --confirm` → pre-migration tree, then `migrate --confirm` succeeds.
Temporary HOME to the Trash.

### Checkpoint (gate): module review
Then push and PR with the user's approval; the round-2 coordinator reviews; the user merges after CI is green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Putting back moves the wrong directory | High | journal step per move with `existed`; tests per step compare whole-tree digests |
| A swapped `data/` loses a file the runtime had | Medium | stage starts from a copy of the target's `data/`; digest test with a pre-existing file |
| flock semantics on macOS | Low | test holds the lock from the same process via a second descriptor |
