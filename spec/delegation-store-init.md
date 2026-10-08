# Spec: delegation-store-init

## Objective

Found during the `delegation-claim` live check (2026-10-09) and reproduced with main's code (3 failures in 10 rounds of
3 processes): processes that open a brand-new delegation state root at the same moment can fail with
`delegation database schema is incomplete` or `state directory could not be created`. It fails closed (no host is
reached), but a delegation command then errors for no reason. Worse, a creator that dies between creating the empty
database file and creating its tables leaves a file every later open refuses forever. The user chose (2026-10-09) to fix
this as its own module.

Readers: the user; the round-2 coordinator, who reviews the PR before the user merges.

## What exists today (main 608d55f, 2026-10-09)

- `hooks/session_delegation.py:311-316` `DelegationStore.__init__`: `_prepare_root()` then `_prepare_database()`.
- `:318-340` `_prepare_root`: if the path exists, check it (not a symlink, a directory, owned, 0700); else
  `mkdir(parents=True, mode=0o700)` — a second process racing here gets `FileExistsError` →
  `DelegationError("state directory could not be created")`.
- `:356-374` `_prepare_database`: if the file exists, check its metadata; else create it with `O_CREAT|O_EXCL` (0600)
  and mark `created`; only the creator runs `_initialize_schema` (`:415-466`, `BEGIN IMMEDIATE` … `PRAGMA user_version
  = 2` … `COMMIT`); everyone runs `_validate_schema` (`:468-490`), which refuses `user_version != 2` or missing tables.
  A process that finds the creator's empty file before its `BEGIN IMMEDIATE` sees version 0 and no tables and fails.

## Assumptions (accepted by the user 2026-10-09)

1. Directory: a `FileExistsError` from `mkdir` is not an error; the existing-directory checks (not a symlink, a
   directory, owned by the user, 0700) then run as for a directory that was already there.
2. Schema: every opener, not only the file's creator, initializes inside `BEGIN IMMEDIATE`, and only when
   `user_version` is 0 and there are no tables; otherwise it leaves the database to validation. The first to take the
   write lock creates the tables; the others wait (busy timeout) and then see a complete database. An empty file left
   by a creator that died before its tables is initialized by the next opener.
3. A database with content and the wrong schema (for example version 0 with another table) is still refused; the
   0600, owner and sidecar checks are unchanged.
4. Schema stays 2; `interface.json` unchanged; hooks only; no release in this module.
5. Red first: several real processes, several rounds, opening a fresh state root at once → no error (main fails);
   a 0-byte database file → initialized; version 0 with another table → refused; existing tests green; validate on
   Python 3.9, 3.10, 3.14. The multi-process test is the live check (real processes); no separate temporary-HOME run.
6. The round-2 coordinator reviews the PR; the user merges after every CI check has finished green.

## Decisions

- **D127 directory race.** `_prepare_root` tries `mkdir(parents=True, mode=0o700)` + `chmod(0o700)` when the path is
  missing; on `FileExistsError` it falls through to the existing-path checks (the same code path as a directory that was
  already there). Other `OSError`s keep `state directory could not be created`.
- **D128 initialize if empty.** `_initialize_schema` becomes `_initialize_if_empty` and runs for every opener before
  `_validate_schema`: `BEGIN IMMEDIATE`; read `user_version` and the table names; if the version is 0 and there are no
  tables, create the two tables and set version 2; `COMMIT` (or `ROLLBACK` when there was nothing to do). The table
  definitions are unchanged. `_prepare_database` still creates the file with `O_EXCL` (a `FileExistsError` there means
  another process created it: fall through to the metadata check).
- **D129 docs.** CHANGELOG `[Unreleased]`; interface doc delegation storage row if it describes initialization.

Review correction (after #43 merged): D128's empty check counts every schema object not named `sqlite_%` (a view,
index or trigger makes a database not empty), and a database whose `user_version` is not 0 is left to validation
without taking the write lock (read once without a lock, checked again under `BEGIN IMMEDIATE` only at 0).

## Requirements

0. Red first (new `hooks/test_delegation_store_init.py`):
   - 8 rounds × 4 real processes opening one fresh state root at the same moment (a start barrier file) → every
     process succeeds and the database validates (fails on main);
   - a pre-created 0-byte database file (0600) → opening initializes it, version 2;
   - a database at version 0 with an unrelated table → `schema is incomplete`, unchanged;
   - a state path that appears between the existence check and `mkdir` (simulated) → accepted when it is a private
     directory, refused when it is a symlink.
1. Existing `test_session_delegation*.py`, `test_delegation_claim.py` stay green unchanged.
2. Validate on Python 3.9, 3.10, 3.14; CI green (all checks finished).

## Boundaries

- Always: temporary state roots in tests.
- Ask first: the real `~/.agent-relay/delegation`.
- Never: relax the directory, file or sidecar checks; change the schema; merge before the coordinator's review and
  finished CI.

## Success criteria

Any number of processes may open a new delegation state root at once and all succeed with the same complete database;
an empty database left by a crash is completed, while a foreign or damaged one is still refused.

## Open questions

None. Assumptions 1–6 accepted on 2026-10-09 ("成立"); the spec (D127–D129) accepted on 2026-10-09 ("接受").
