# Spec: delegation-sidecar-race

## Objective

During the codex-gated-wake checkpoint (`tasks/codex-gated-wake/todo.md`, 2026-10-08), `scripts/validate.sh` on
Python 3.14.3 failed once in an untouched test: `test_session_delegation.py`
`ClaimAndStateTests.test_concurrent_retry_keeps_one_host_creation_claim` with
`failures == [FileNotFoundError(2, 'No such file or directory')]`; 8 isolated reruns and a full rerun passed. Find the
race and remove it.

Readers: the user; whoever runs `validate.sh` next.

## What exists today (measured, main 55c6bad, 2026-10-08)

`hooks/session_delegation.py` `DelegationStore._check_sidecars` runs before every connection opens and after it closes.
For each of `-journal`, `-wal`, `-shm` it calls `path.exists()`, then `path.lstat()`, and rejects symlinks, non-regular
files, foreign owners and modes other than 0600. The store uses SQLite's default rollback journal (DELETE mode): every
write transaction creates `delegation.sqlite-journal` and deletes it on COMMIT. When one worker sees the journal in
`exists()` and another worker's COMMIT deletes it before `lstat()`, `lstat()` raises a raw `FileNotFoundError`.

It is a race in the store, not in the test: any two threads or processes using one state root can hit it. The test's
four threads just make it likely.

## Assumptions

1. A sidecar that disappears between noticing it and reading its metadata is treated as absent, the same as one that
   never existed.
2. The unsafe-sidecar rejection is unchanged: symlink, non-regular file, foreign owner, mode other than 0600.
3. No interface change; no journal-mode change (switching to WAL would change which sidecars exist and is out of scope).
4. Other `exists()` → `lstat()` sites (`session_delegation_claude.py`, `host_backup.py`,
   `native_collaboration_adapters.py`, `native_collaboration_runtime.py`, `host_config_removal.py`) read user or host
   config files that nothing deletes in normal operation; they are out of scope.
5. Release number is decided at release.

## Decisions

- **D71 a vanished delegation-store sidecar is absent, not an error.** `_check_sidecars` calls `lstat()` directly and
  skips the suffix on `FileNotFoundError`; every other `OSError` still propagates.

## Requirements

1. Test (`test_session_delegation.py` `PrivateStoreTests`), red first: a real 0600 `-journal` is deleted just before
   `lstat()` reads it (the interleaving of a concurrent COMMIT); `count_delegations` returns 0 instead of raising.
   Red on the current code with the same `FileNotFoundError`.
2. `test_unsafe_sidecar_is_rejected_before_database_open` still passes.
3. The original concurrent test passes 300 runs in a row on Python 3.14.
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14. Bridge `npm run check` is not affected (Python only); run it
   if `node_modules` is present.
5. CHANGELOG `[Unreleased]` entry.

## Boundaries

- Always: unsafe sidecars stay rejected.
- Ask first: the real `~/.agent-relay`, `~/.claude`, `~/.codex`.
- Never: push without approval.

## Success criteria

The deterministic test is red before and green after the fix; `validate.sh` green on the three Pythons.

## Open questions

None.
