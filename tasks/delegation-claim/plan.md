# Plan: delegation-claim

Based on [`spec/delegation-claim.md`](../../spec/delegation-claim.md) (accepted by the user on 2026-10-08:
assumptions 1–10, D122–D126). Branch `claude/delegation-claim` from main 842b672. Red → green, one commit per task.
The round-2 coordinator reviews the PR; the user merges after every CI check has finished green. No release here.

Code: `hooks/session_delegation.py` (`OperationClaim`), `hooks/session_delegation_control.py` (controller). Tests: new
`hooks/test_delegation_claim.py`. No bridge change. Record validate only after its output says `validate: pass`.

## Task List

### Task 1: the claim file (D122)
Red first: `OperationClaim` creates `claims/` 0700 and the file 0600; a second holder (another descriptor) →
`OperationBusy`; `begin` writes and `previous()` reads it back after reopening; `end` empties it; a symlinked lock file
or a non-regular one → `DelegationError("claim-file-unsafe")`. Then the class.

### Task 2: the controller takes the claim; busy and interrupted results (D123, D124, D125)
Red first with a fake adapter: create and continue while the claim is held → adapter not called,
`operation-in-progress`, state unchanged; leftover `create` on a `creating` row and leftover `continue` on a
`completed` row → `unknown` row, `previous-operation-interrupted`, adapter not called, file empty; `held` → file empty
and a second create proceeds; adapter raising → file empty; two real processes creating the same launch key with a
blocking fake adapter → one adapter call in total. Then the controller changes. Existing delegation tests unchanged.

### Checkpoint (report): validate on one Python

### Task 3: docs (D126)
Session-delegation skill (the two prerequisites and what to do), interface doc delegation rows, CHANGELOG.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 4: live check
Temporary HOME, the controller CLI with a fake host backend (no real session): two concurrent `create` processes →
one launch; a planted leftover operation → `previous-operation-interrupted`. Temporary HOME to the Trash.

### Checkpoint (gate): module review
Then push and PR with the user's approval; the round-2 coordinator reviews; the user merges after CI has finished green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A real launch path bypasses the controller | High | grep every `adapter.create` / `continue_turn` caller; both go through the controller |
| The leftover marker misfires on a normal error | Medium | `end()` in `finally`; only a dead process leaves the marker; test with a raising adapter |
| The live check would need a real host | Medium | fake backend injected at the adapter factory; no session started |
