# Spec: delegation-status-read-only

## Objective

Second module of 0.6.3. From the round-2 coordinator's acceptance of 0.6.2 (2026-10-10, low): in Codex's default
sandbox the read-only `status` answered `state-not-writable`. Looking at a delegation must not need write access.

## What exists today (main 72ee153)

`session_delegation_control.py` opens `DelegationStore(args.state_root)` for every command; the store prepares its
directory and database for writing, and a failure becomes `{"state": "error", "reason": "state-not-writable"}` (D160).
`status` of a Claude target also advances the record from what the host shows (`_reconcile_lifecycle`).

## Assumptions (accepted by the user 2026-10-10)

1. When the delegation store exists but cannot be written, `status` and `list` open it read-only (SQLite `mode=ro`,
   no directory or file is created or changed) and answer from the stored record, with `readOnly: true` in the output.
2. A read-only `status` does not advance the record: it reports the stored state and the host status it can observe,
   and says the stored state may be behind. `create`, `continue`, `cancel` and `prune --confirm` still answer
   `state-not-writable`; `prune` without `--confirm` and `resolve` (both read-only) follow rule 1.
3. A store that needs migration (older schema) or does not exist is not created or migrated by a read-only command: the
   answer names the reason (`list` on an absent store stays the empty list, as today). The store uses SQLite's
   default rollback journal: when a writer died and left a hot journal, a read-only open cannot roll it back. If the
   read-only open or any read fails, the answer is an error with a reason (`state-not-readable`) — never an empty
   result, and never a retry with `immutable` or any mode that could read half-written data.
4. Only the plugin's hooks change; no runtime upgrade. The session-delegation skill says `status` and `list` work from
   Codex's sandbox without escalation.

## Decisions

- **D189 looking at delegations needs no write access.** Assumptions 1–3.

## Requirements

1. Red first, with the D160 sandbox fixture (`sandbox-exec` denying writes below the state root): `status`, `list`,
   `resolve` and `prune` (preview) answer with `readOnly: true` and leave every file's bytes and mtime unchanged;
   `create`, `continue`, `cancel`, `prune --confirm` answer `state-not-writable`; a schema-2 store read-only names
   the migration; a store whose read-only open fails (a leftover hot journal) answers `state-not-readable`, not an
   empty result; a writable store behaves exactly as today (no `readOnly`).
2. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Never: write, migrate or create anything from a read-only command; report a state the store does not hold.

## Open questions

None. Accepted by the user on 2026-10-10; spec review by the round-2 coordinator pending. The plan is written when this
module becomes current.
