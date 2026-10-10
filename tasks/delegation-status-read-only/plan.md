# Plan: delegation-status-read-only

Based on [`spec/delegation-status-read-only.md`](../../spec/delegation-status-read-only.md) (accepted by the user on
2026-10-10: assumptions 1–4, D189; reviewed by the round-2 coordinator in #82/#83). Branch
`claude/delegation-status-read-only` from main after this plan's PR. Second and last module of 0.6.3; hooks only, no
runtime upgrade. The round-2 coordinator is told every PR number.

## Task List

### Task 1: a read-only store
Red first (`test_session_delegation.py`, plus the D160 `sandbox-exec` fixture in `test_delegation_state_writable.py`):
`DelegationStore(root, read_only=True)` on a current store reads claims and envelopes and changes no file (bytes and
mtime of the database, its directory and any sidecar unchanged; no `-journal` appears); it never creates the directory
or the database, never initializes or migrates; every writing method raises `StateNotWritableError`; a schema-2 store
raises a `DelegationError` naming the migration; a database with a leftover hot journal (a copied mid-transaction
journal) raises `state-not-readable` instead of returning rows; an absent store raises the existing "unavailable"
error. Green: the store opens `file:<path>?mode=ro` (URI), keeps the ownership and mode checks, skips
`_initialize_if_empty` / `_migrate_if_needed`, validates the schema version, and maps a failed open or read to
`state-not-readable`. No `immutable`, no retry in another mode.

### Task 2: the controller falls back for read-only commands
Red first (same sandbox fixture, end to end through `session_delegation_control.py`): with the state not writable,
`list`, `resolve`, `prune` (no `--confirm`) and `status` answer from the store with `readOnly: true`; `status` reports
the stored state, does not advance it, and adds one sentence that the stored state may be behind (it observes the host
only through calls that write nothing; when the host cannot be asked from the sandbox its status is `unknown`);
`create`, `continue`, `cancel`, `prune --confirm` still answer `state-not-writable`; a writable store answers exactly
as today, without `readOnly`; `state-not-readable` and the migration reason come out as `{"state": "error", "reason":
…, "detail": …}`. Green: `main` opens writable first and, only for those four read-only commands and only on
`state-not-writable`, opens read-only; the status path uses the stored claim instead of the adapter's reconciling
`status`.

### Task 3: skill and CHANGELOG
session-delegation skill: `status` and `list` work from Codex's default sandbox without escalation; what `readOnly` and
`state-not-readable` mean (guard test). CHANGELOG `[Unreleased]`.

### Checkpoint (report): local validation and one real check
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 (Node 24 first on PATH). Real check on this Mac, read-only: under
`sandbox-exec` denying writes below a copy of the real delegation store, `list` and `status --name <an existing name>`
answer with `readOnly: true` and the copy's files are unchanged.

### Task 4: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.3 release PR.
