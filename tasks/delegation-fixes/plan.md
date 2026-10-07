# Plan: delegation-fixes

Based on [`spec/delegation-fixes.md`](../../spec/delegation-fixes.md) (D15–D17 accepted by the user on 2026-10-07;
D18 for round 1 finding 7 added by the project owner; live checks run by the agent). Repository `/Users/vilin/Documents/haigeerlab/agent-relay`, local only.
Reread [`docs/collaboration-split-brief.md`](../../docs/collaboration-split-brief.md) after any context reset.

**Start condition:** met — integration round 1 passed on 2026-10-07
([record](../../docs/acceptance/2026-10-07-round1.md)).

## Overview

Finding 3 first (pure controller logic, no host needed), then finding 7 (it blocks every Codex → Claude second
round on Claude Code 2.1.291, so finding 4 cannot be seen before it), then capture the real Claude host entry,
then finding 4 from that evidence, then docs, then one live run of C3 and C7.

## Architecture Decisions

- D15 (revised at Task 1) lives in the controller's `_resolve` only: when any name match has a `host_ref`, drop
  the matches without one; otherwise match as today. Held rows are not changed, so the same-key retry stays.
  Launched rows, including cancelled ones, are matched exactly as today (C6 unchanged).
- D16 lives in each adapter's `cancel` (both already branch on `host_ref is None`).
- D17: one module-level predicate in `session_delegation_claude.py` over `(state, status)`, used by
  `_reconcile_lifecycle` and `continue_turn`; unknown pairs are busy.
- D18 lives in the Claude adapter: one helper "rebind a late entry" used at the top of `status` and
  `continue_turn` for `unknown` rows with `host_ref` and no `host_session_ref`; it reuses `_exact_session`'s checks
  and `bind_host`.
- No schema, state or evidence-word change. Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: Held create leaves no blocking record (D15)

**Description:** Prove-It test: a create whose adapter answers `held` without a host reference, then a create with
the same name — today the second lookup is `session-name-ambiguous`. Fix in `_resolve`; answer stays `held` with
the prerequisite, and the same-key retry test stays green. A lone never-launched match still resolves by name.

**Acceptance:** spec requirements 1–2; C6 regression test (two launched same-name sessions still ambiguous) green.

**Verify:** `scripts/validate.sh`; mutation: remove the `_resolve` filter → the same-name test goes red.

**Files:** `hooks/session_delegation_control.py`, `hooks/test_session_delegation_recovery.py`

### Task 2: Cancel of a never-launched row (D16)

**Description:** Prove-It test: a `creating` row with no host reference cancels as `unknown` today. Both adapters
move it to `cancelled` and answer `cancelled`; launched rows still need host confirmation. Skill cancel paragraph
states the narrowed rule.

**Acceptance:** spec requirement 3; existing launched-cancel tests unchanged and green.

**Verify:** `scripts/validate.sh`.

**Files:** `hooks/session_delegation_claude.py`, `hooks/session_delegation_codex.py`, their tests,
`skills/session-delegation/SKILL.md`

### Checkpoint (report): finding 3 fixed in unit tests

### Task 3: Late Claude entry is bound on the next call (D18)

**Description:** Prove-It test: create where the fake host lists the background entry only after the create call
returns → today `unknown`, and `continue` raises `delegation-is-not-ready-for-follow-up`. Add the rebind helper;
`status` then answers `created`, and `continue` proceeds. Negative tests: entry still absent → `unknown`; entry
with another session prefix or cwd → `unknown`, nothing bound.

**Acceptance:** spec requirement 5.

**Verify:** `scripts/validate.sh`; mutation: drop the helper call from `status` → the late-entry test goes red.

**Files:** `hooks/session_delegation_claude.py`, `hooks/test_session_delegation_claude.py`

### Checkpoint (report): finding 7 fixed in unit tests

### Task 4: Capture the Claude host entry (live, read-only)

**Description:** In a throwaway project under the scratchpad, start one background Claude session with a short
prompt, wait until it finishes its first turn, and record `claude agents --json --all --cwd <project>` while it is
idle, and record how long after `claude --bg` returns the entry first appears (finding 7); send it a second short turn and capture once while working if feasible. Stop the session. Store the entries
as fixtures with ids replaced. Record the Claude version.

**Acceptance:** fixtures committed; todo records the observed `(state, status)` pairs and whether assumption 1 holds.
If it does not, update the spec before Task 5.

**Verify:** `scripts/validate.sh` still green; session stopped (`claude agents --json --all` shows it not running).

**Files:** `hooks/fixtures/` (or the test file's inline fixtures, matching the existing style), `tasks/delegation-fixes/todo.md`

### Task 5: One Claude idle predicate (D17)

**Description:** Prove-It test: `continue` against the captured idle entry answers `target-busy` today. Add the
predicate, use it in both places, name an unknown state in the held answer.

**Acceptance:** spec requirement 4; a working capture (or the existing busy fixtures) still gives `target-busy`.

**Verify:** `scripts/validate.sh`; mutation: restore the old reconcile condition → the round-two test goes red.

**Files:** `hooks/session_delegation_claude.py`, `hooks/test_session_delegation_claude.py`

### Checkpoint (report): finding 4 fixed in unit tests

### Task 6: Docs

**Description:** Interface §10 "Held create" and "Claude round two" rows, a row for round 1 finding 7, and the findings table point to this
module as done; checklist C3/C7 current column updated.

**Acceptance:** spec requirement 6.

**Verify:** `scripts/validate.sh`; `git diff --stat` touches only the listed docs.

**Files:** `docs/collaboration-interface.md`, `docs/acceptance/checklist.md`

### Task 7: Live C3 and C7

**Description:** With the agent-relay runtime ready, in a throwaway project: C7 (create while a prerequisite is
missing, then add the temporary allow rules, create again with the same name, status and cancel without
disambiguator) and C3 Codex → Claude (create, `status` until `created`, result, `continue` round two, read-only negative). Clean up sessions, identities and
allow rules; record in todo.

**Acceptance:** spec success criterion 2.

**Verify:** recorded evidence (states, prerequisites, message ids); cleanup listed.

**Files:** `tasks/delegation-fixes/todo.md`

### Checkpoint (gate): module review

## Risks

- The capture shows a different cause → spec updated first, Task 5 re-planned at that point.
- Live C3 needs a Codex origin with agent-relay installed (round 1 kept design-test and the Codex entry); if it is gone, Task 7 records the
  Claude-origin part and asks before reinstalling anything.
