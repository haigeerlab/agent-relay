# Spec: state-migration-safety

## Objective

`state_migration.py migrate --confirm` moves Spec Guard-era collaboration data (`~/.spec-guard/native-collaboration`,
`~/.spec-guard/session-delegation`) into agent-relay once per Mac. The 0.4.0 architecture review (B6, C11) found that
it is neither exclusive nor recoverable, and reading it again for this module found a worse case: it never checks
agent-relay's own bridge, yet it unlinks the target mailbox (`bridge.sqlite`, `-wal`, `-shm`) and copies a new file in
place, so a running bridge can lose writes or keep serving a deleted file. A failure or a kill between the mailbox copy
and the delegation copy leaves a target mailbox with data, which every later run refuses ("never merged"), with no way
back. The user chose (2026-10-08) to fix this as the first remaining review finding. This Mac migrated long ago, so the
change matters for users who still have to migrate; the real host is not touched.

Readers: the user; the round-2 coordinator, who reviews the PR before the user merges.

## What exists today (main bf72a2d, 2026-10-08)

- `hooks/state_migration.py:126-152` `inspect`: snapshots old databases (never opens them in place), counts rows,
  lists blockers: nothing to migrate, running **old** bridges (`_running_servers(old_runtime)`, `:103-106`), target
  runtime not ready, target mailbox with messages or agents, target delegation database present. No lock; no check of
  agent-relay's own bridges.
- `:217-275` `migrate`: re-runs `inspect`; backup `backups/<UTC second>` (blocked if it exists); snapshot → backup →
  copy into place: unlink the target `bridge.sqlite` (+ `-wal`, `-shm`) and `_sqlite_copy`, copy daily backups,
  `copytree(data, dirs_exist_ok=True)` over `runtime/data`, copy the delegation database into `delegation/`; then
  compare table counts and `runtime_status`; a mismatch returns `verification-failed` and leaves everything in place.
- `:292-321` CLI: `detect`, `migrate --confirm [--acknowledge-stale ID]`; exit 0 only for `migrated`.
- `hooks/native_collaboration_runtime.py:346` `_servers_running(root)` counts bridges of a runtime;
  `:421-460` the runtime swap journal (`runtime-swap.json`, mkstemp + fsync + replace, 0600) is the pattern reused here.
- Tests: `hooks/test_state_migration.py` (13); `test_a_count_mismatch_is_reported_and_nothing_is_removed` (`:199`)
  expects the old "leave it in place" behaviour.
- Docs: `docs/collaboration-interface.md` §13 rows "Migration" and "Migration safeguards" (`:246-247`); README `:150`;
  collaboration-ops skill `:142-151`.

## Assumptions (accepted by the user 2026-10-08)

1. The whole migration holds an exclusive `fcntl.flock` (as built: on the `~/.agent-relay` directory itself, see D116);
   a second run that cannot take it is refused. The kernel releases the lock when the process dies, so no stale lock
   is left.
2. Agent-relay's own bridges are checked too (`_servers_running` of the target runtime): `detect` lists them as a
   blocker and `migrate` refuses. The old-bridge check stays.
3. Everything to be written is prepared first in `~/.agent-relay/.state-migration-<stamp>-<hex>/`: the whole
   `mailbox/` (old snapshot, old daily backups, plus the target's existing backup files), the whole `data/` (the
   target's existing content with the old data copied over it), and `delegation/` (the old database plus any other
   files already in the target directory). Table counts are checked there before anything is swapped.
4. The swap replaces whole directories: for each of the three, the current one is moved into the stage, then the
   prepared one is moved into place; then counts and runtime status are checked again. A journal
   `~/.agent-relay/state-migration.json` (same writer as `runtime-swap.json`) is written before every step. Any error,
   or a count mismatch, puts everything back. This changes today's behaviour: a mismatch no longer leaves the copied
   data in place with `verification-failed`; it rolls back and reports the mismatch.
5. A killed migration leaves the journal: `detect` and `migrate` report `interrupted`, `migrate` refuses, and a new
   `state_migration.py recover --confirm` puts the pre-migration layout back from the journal. Back only, never forward.
6. The timestamped `backups/<stamp>` stays as it is. The old `~/.spec-guard` directories stay read-only: every read goes
   through a copy and their bytes never change.
7. `interface.json` stays 1.4 (the migration tool is not part of what Spec Guard consumes); interface doc §13, README
   and the collaboration-ops skill are updated.
8. No bridge change, no manifest regeneration; the real host is not touched; no release in this module.
9. Red first (see Requirements); validate on Python 3.9, 3.10, 3.14; a live migration and a killed one recovered in a
   temporary HOME.
10. The round-2 coordinator reviews the PR before the user merges.

## Decisions

- **D116 lock.** `migrate` and `recover` open the state root `<parent>` directory read-only and take
  `fcntl.flock(LOCK_EX | LOCK_NB)` on it; `BlockingIOError` → result `{"state": "blocked", "diagnostic": "another state
  migration is running"}`. The lock is held until the call returns. Build correction: the spec first named a
  `state-migration.lock` file, but creating it is a write, and the existing tests require that a blocked migration
  writes nothing; locking the directory (exclusive on macOS, checked) needs no file. Without a state root the runtime
  cannot be ready, so `migrate` only inspects and returns blocked. `detect` takes no lock.
- **D117 own bridges.** `inspect` gains `target_count: Callable[[Path], int]` (default
  `native_collaboration_runtime._servers_running`) and adds the blocker "N agent-relay bridge server process(es) are
  running; close every session using the mailbox first"; `Report.target_servers` reports the count.
- **D118 stage and journal.** Stage `<parent>/.state-migration-<stamp>-<6 hex>` created with `mkdir` (no `exist_ok`).
  Items, in order: `mailbox` (`runtime/mailbox`), `data` (`runtime/data`), `delegation` (`<parent>/delegation`); an item
  is skipped when there is nothing old to bring (no old mailbox → no `mailbox`/`data`; no old delegation → no
  `delegation`). Journal `<parent>/state-migration.json` (0600, mkstemp + fsync + replace): `{stamp, stage, backup,
  items: [{name, target, existed}], counts: {mailbox, delegation}, step: {item, phase}}` with phase `retiring`
  (current → `stage/previous-<name>`) or `placing` (`stage/<name>` → target), rewritten before each move, then
  `verifying`. `existed` records whether the target existed, so putting back knows whether to restore or remove.
- **D119 put back.** On any exception or mismatch after the first journal write, and in `recover`: for each journalled
  item in reverse, if `stage/<name>` is missing and the target exists and the item reached `placing`, move the target
  back to `stage/<name>`; then if `stage/previous-<name>` exists move it to the target (else, when `existed` is false,
  leave the target absent). Then remove the journal and keep the stage renamed as
  `.state-migration-failed-<stamp>` for inspection (never deleted automatically). Result `{"state": "rolled-back",
  "diagnostic": …, "mismatches": […], "kept": <failed stage>}`, exit 1. A failure before the first journal write removes
  only this call's stage.
- **D120 interrupted and recover.** `inspect` reports `interrupted` with the journal when it exists (blocker "a state
  migration stopped half way; run state_migration.py recover --confirm"); `migrate` refuses. CLI `recover` requires
  `--confirm`, takes the lock, refuses without a journal or while either bridge runs, runs D119 and returns
  `{"state": "recovered", "kept": …}` (exit 0).
- **D121 docs.** Interface doc §13 "Migration" / "Migration safeguards" rows (lock, own bridges, all-or-nothing,
  `recover`); README migration commands; collaboration-ops skill (`recover --confirm` only after the user agrees; never
  move the directories by hand); CHANGELOG `[Unreleased]`.

## Requirements

0. Red first (`test_state_migration.py`, new `test_state_migration_safety.py`):
   - a second `migrate` while the lock is held (taken by the test) → blocked "another state migration is running",
     nothing written;
   - agent-relay bridges running (injected count) → `detect` blocker, `migrate` blocked, nothing written;
   - a failure injected at each journalled step (each item × `retiring` / `placing`, and `verifying`) and a count
     mismatch → result `rolled-back`, the target tree (mailbox, data, delegation) byte-identical to before, no journal,
     the failed stage kept, old directories unchanged;
   - a simulated kill (journal written at a step, layout as that step leaves it, no rollback) → `detect` shows
     `interrupted`, `migrate` refuses, `recover --confirm` restores the pre-migration tree and removes the journal;
     `recover` without a journal or with a running bridge refuses;
   - a successful migration still produces the same target content and backup as before.
1. Existing tests stay green except `test_a_count_mismatch_is_reported_and_nothing_is_removed`, whose expectation
   changes to D119 (renamed accordingly).
2. Validate on Python 3.9, 3.10, 3.14; CI green.
3. Live check in a temporary HOME: build a Spec Guard-era layout (mailbox with rows, delegation database), install a
   runtime from this branch, `migrate --confirm` → migrated, counts equal, old tree unchanged; a second layout where a
   child process dies with `os._exit` right after the `placing` journal write of `mailbox` → `detect` interrupted,
   `recover --confirm` → the pre-migration tree, then `migrate --confirm` succeeds.

## Boundaries

- Always: temporary HOME in tests; old directories read only through copies; journal before every move.
- Ask first: the real `~/.agent-relay` and `~/.spec-guard`.
- Never: roll a migration forward; delete a stage, backup or failed stage automatically; change `interface.json`;
  merge before the round-2 coordinator's review.

## Success criteria

No concurrent run, running bridge, failure or kill leaves agent-relay's target half migrated: either the migration
completes with matching counts, or the target is exactly as before (directly, or after `recover --confirm`), and the
old Spec Guard directories are never changed.

## Open questions

None. Assumptions 1–10 accepted on 2026-10-08 ("成立，接口不升版本"); the spec (D116–D121) accepted on 2026-10-08 ("接受").
