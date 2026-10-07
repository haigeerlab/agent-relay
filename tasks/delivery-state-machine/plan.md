# Plan: delivery-state-machine

Based on [`spec/delivery-state-machine.md`](../../spec/delivery-state-machine.md) (accepted by the user on 2026-10-07:
24 h default, evidence may resolve `unknown`, interface stays 1.0). Branch `claude/delivery-state-machine` from
main d2a71f3.

## Overview

Make bridge TS tests part of the loop first, then schema v3 with the Python readers, then the transition core,
then route every writer through it (wake results, expiry, ack), then surface it, then the upgrade command, then
docs and live checks. Every task is red → green; bridge changes update `UPSTREAM.sha256` and `UPSTREAM.md` in the
same commit.

## Architecture Decisions

- Development builds the bridge in place (`plugins/agent-relay/bridge/node_modules`, `dist/` are git-ignored by the
  vendored `.gitignore` and skipped by `verify_bridge_copy`).
- `scripts/validate.sh` runs the bridge's `npm run check` when `bridge/node_modules` exists and reports it as one
  extra line; otherwise it prints that the TS suite was skipped (CI-less repo: the PR states which ran).
- One TS module `src/delivery.ts` holds the state type, the transition table and `transition(db, id, to, evidence)`;
  `WakeQueue` and `BridgeStore` call it inside their existing transactions.
- Verification for every task: `validate.sh` (Python + TS when built).

## Task List

### Task 1: TS suite in the loop
`npm ci` in `bridge/`; `validate.sh` runs `npm run check` there when built. **Accept:** 70 upstream tests reported
by `validate.sh`. **Files:** `scripts/validate.sh`.

### Task 2: Schema v3 and Python readers
Additive `MIGRATIONS[2]`: nullable `delivery_state`, `delivery_changed_at`, `read_at`, `expires_at` on `messages`;
`SCHEMA_VERSION = 3`. Old-process INSERT test extended. Python `native_collaboration_retire`,
`session_delegation_backend` accept 2 and 3; `state_migration` non-final set. **Accept:** spec reqs 1, 6.
**Files:** `bridge/src/schema.ts`, `bridge/test/schema.test.ts`, three hooks + tests, `UPSTREAM.*`.

### Task 3: Transition core (D28)
`src/delivery.ts`: states, table, `transition()`; send writes `queued` and `expires_at` (D27 default and
`expiresInSeconds`). Tests: every allowed and refused transition. **Accept:** spec req 2. **Files:**
`bridge/src/delivery.ts`, `bridge-store.ts`, `server.ts` (send schema), new `test/delivery-state.test.ts`.

### Task 4: Wake results drive the message state, `unknown` never replayed
`claim` / `finish` / adapter mappings call `transition()`: `sending`, `accepted`, `failed`, `unknown`, `held` →
stays `queued`; late receipt and recipient fetch resolve `unknown` → `accepted`. **Accept:** spec req 3.
**Files:** `wake-queue.ts`, `wake-dispatcher.ts`, tests.

### Checkpoint (report): state machine drives every wake outcome

### Task 5: Expiry and inbox filters (D27)
Sweep `queued` past `expires_at` → `expired`, cancel its job, never ping; `bridge_inbox` / `bridge_wait` hide it
unless `includeExpired`; accepted messages never expire. **Accept:** spec req 4. **Files:** `wake-queue.ts`,
`bridge-store.ts`, `server.ts`, `inbox-waiter.ts`, tests.

### Task 6: Ack closes the wake job (finding 5)
`ack()` moves the job to `acknowledged`; update the pinned upstream test deliberately. **Accept:** spec req 5.

### Task 7: Surface the state (D29)
`bridge_send` `deliveryState`; outbox and wake status show it; tool descriptions state no exactly-once.
**Accept:** spec D29.

### Checkpoint (report): bridge side complete

### Task 8: Upgrade command (bridge-vendoring D26)
`native_collaboration_runtime.py upgrade --confirm` with fake-runtime tests: refuses while a server runs, backup
first, stage from the verified copy, move `mailbox/` and `data/`, swap, verify `ready`+`current` and row counts,
keep the previous directory, roll back on failure. **Accept:** spec req 7. **Files:**
`native_collaboration_runtime.py`, tests, `collaboration-ops` skill.

### Task 9: Docs and provenance
`UPSTREAM.md` change list, README (exactly-once, timeout, upgrade), interface §3/§5 rows and gaps a/b/c/finding 5
done, checklist B4/B5/D12/D13 wording. **Accept:** spec req 8.

### Task 10: Live checks (coordinator, user go-ahead)
Temporary root: install, v2→v3 migration with counts; B4/B5 states; D12; D13 with a short timeout. Real-runtime
upgrade only if the user says so. **Accept:** spec success criterion 3.

### Checkpoint (gate): module review
