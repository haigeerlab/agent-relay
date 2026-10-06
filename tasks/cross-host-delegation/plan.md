# Plan: cross-host-delegation

Based on [`spec/cross-host-delegation.md`](../../spec/cross-host-delegation.md) (reviewed by the user on
2026-10-07, D11 and D12 accepted). Repository `/Users/vilin/Documents/haigeerlab/agent-relay`, branch `main`,
local only. Reread [`docs/collaboration-split-brief.md`](../../docs/collaboration-split-brief.md) after any context
reset.

## Overview

Rename in two groups that each keep the suite green: the result route (key, idempotency prefix, route tag) and the
state root first, then the backend-specific names (control tags, Codex private server and service). Interface rows
last.

## Architecture Decisions

- Each renamed string becomes a module constant where it is used more than once, so producer and validator cannot
  drift (the result key prefix is produced in the backend and validated in the controller: one constant in the
  backend, imported by the controller).
- Tests assert literals, not the constants under test.
- Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: Result route and state root

**Description:** `RESULT_KEY_PREFIX = "agent-relay-result:"` in `session_delegation_backend.py`, used by the
controller's validation regex; idempotency prefix `agent-relay-result-send:`; `<agent-relay-result-route>` tags;
`default_state_root()` → `~/.agent-relay/delegation` with the parent created 0700 when absent if the controller
creates it today (otherwise unchanged behavior). Move pinned assertions; add the old-prefix refusal test.

**Acceptance:** suite green (219, +1 if a root test is needed); mutation: old prefix restored → refusal test red.

**Verify:** `scripts/validate.sh`; the mutation.

**Files:** `session_delegation_backend.py`, `session_delegation_control.py`, related tests

### Task 2: Control tags and Codex private names

**Description:** `<agent-relay-control>` in the Claude and Codex backends; Codex private server
`agent_relay_delegation`, service name `agent_relay_session_delegation`, title "agent-relay Session Delegation";
the parameterized server-name test (`test_session_delegation_claude.py:140-155`) uses `agent-relay`. Move pinned
assertions.

**Acceptance:** suite green; name scan clean except the three deliberate lines.

**Verify:** `scripts/validate.sh`; name scan recorded in todo.md.

**Files:** `session_delegation_claude.py`, `session_delegation_codex.py`, related tests

### Checkpoint (report): delegation names translated, suite green

### Task 3: Interface rows

**Description:** Update §10 rows that quote the old markers and §13 delegation and migration rows (new root, D12
precondition: migration refused while any delegation is non-terminal).

**Acceptance:** §10/§13 match the code; suite green.

**Verify:** grep of the interface for the old names; `scripts/validate.sh`.

**Files:** `docs/collaboration-interface.md`

### Checkpoint (gate): module review

Stop and report per the brief format. Never pushed.

## Risks

- The controller may create the delegation root with a parent-mode rule different from the runtime's; Task 1 keeps
  whatever it does today and records it, rather than inventing a new rule.
