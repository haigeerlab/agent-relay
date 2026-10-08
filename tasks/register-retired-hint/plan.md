# Plan: register-retired-hint

Based on [`spec/register-retired-hint.md`](../../spec/register-retired-hint.md) (accepted by the user on 2026-10-08:
assumptions 1–4, D64). Branch `claude/register-retired-hint` from main 79b8f23. Red → green, one commit per task.

## Task List

### Task 1: The ownership refusal names a retired state (D64)
Bridge test in `test/identity.test.ts` first: A registers and retires a name; B with `reactivate: true` → refused with
the ownership text, "was retired at <time> by <who>" and "reactivate: true together with takeover: true", row still
retired; an active name owned by A registered by B → refusal without "retired"; B with `reactivate` + `takeover` →
`reactivated: true`. Then `server.ts`: append the retired sentence to the conflict refusal when `existing.retiredAt`.
`UPSTREAM.md` row, `scripts/bridge-manifest.py`, CHANGELOG `[Unreleased]` (needs `upgrade --confirm`).
**Files:** `bridge/src/server.ts`, `bridge/test/identity.test.ts`, `bridge/UPSTREAM.md`, `bridge/UPSTREAM.sha256`,
`CHANGELOG.md`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 2: Live (temporary `AGENT_RELAY_HOME`/HOME, coordinator told first)
Runtime built from this checkout in a temporary root; two stdio sessions; the three cases of Task 1.

### Checkpoint (gate): module review
