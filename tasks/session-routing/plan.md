# Plan: session-routing

Based on [`spec/session-routing.md`](../../spec/session-routing.md) (reviewed by the user on 2026-10-07, D10
accepted). Repository `/Users/vilin/Documents/haigeerlab/agent-relay`, branch `main`, local only. Reread
[`docs/collaboration-split-brief.md`](../../docs/collaboration-split-brief.md) after any context reset.

## Overview

One rename with one owner. Code and tests first (so delegation never breaks between commits), then the skill and
interface text.

## Architecture Decisions

- `BRIDGE_TRANSPORT` lives in `session_routing.py`; delegation imports it. Tests that assert the value use the
  literal `"agent-relay-bridge"` (a test must not derive its expectation from the constant under test), except
  where they only pass the value through.
- Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: Constant, delegation imports, tests

**Description:** Add `BRIDGE_TRANSPORT`; replace the four literals in `session_routing.py`; import it in
`session_delegation_backend.py` and `session_delegation_control.py`; move the pinned assertions in
`test_session_routing.py`, `test_session_routing_entry.py`, `test_session_delegation_backend.py`,
`test_session_delegation_recovery.py`, `test_skill_entrypoints.py`; add the old-value rejection test.

**Acceptance:** 218 tests green; no `spec-guard-bridge` literal in `plugins/agent-relay/hooks/`.

**Verify:** `scripts/validate.sh`; name scan.

**Files:** the three code files and five test files above

### Task 2: Skill and interface text

**Description:** Replace the label in `skills/session-routing/SKILL.md` (4) and `skills/session-delegation/SKILL.md`
(2); update interface §9 target cells to "`agent-relay-bridge` (D1, D10)".

**Acceptance:** no `spec-guard-bridge` anywhere under `plugins/agent-relay/`; entry tests green.

**Verify:** `scripts/validate.sh`; name scan.

**Files:** the two skills, `docs/collaboration-interface.md`

### Checkpoint (gate): module review

Stop and report per the brief format. Never pushed.

## Risks

- An entry test may pin the skill wording that contains the label; Task 1 already runs before the skill edit, so
  such a test is moved in Task 2 together with the text, and both commits stay green.
