# Plan: test-isolation

Based on [`spec/test-isolation.md`](../../spec/test-isolation.md) (accepted by the user on 2026-10-07:
`AGENT_RELAY_HOME`, relative path refused, D21, D22). Branch `claude/test-isolation` from main 60f4ddd.

## Overview

Add the one helper first, then route every entry point through it with a sweep test, then seal the test run, then
docs, then one live moved-root check.

## Architecture Decisions

- `native_collaboration_runtime.state_home()` is the only place that reads `AGENT_RELAY_HOME` or builds
  `~/.agent-relay`; it raises a `ValueError` subclass for a relative path, and each CLI turns that into exit 2 with
  a message naming the variable. `default_root()` = `state_home() / "runtime"`.
- `session_delegation_control.default_state_root()` = `state_home() / "delegation"`; `state_migration` takes the
  target parent from `state_home()` unless `--home` is given for tests (then `<home>/.agent-relay` as today).
- Defaults are computed when a command runs (argparse defaults stay functions of the environment at parse time).
- Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: `state_home()` and derived defaults (D21)

**Description:** Helper with unset / set / empty / relative behaviour; `default_root`, `default_state_root` and the
migration target derive from it; explicit flags still win. Tests for each case, and existing default-path tests
keep passing with the variable unset.

**Acceptance:** spec requirements 1 (derivation part) and 3. **Verify:** `validate.sh`; mutation: helper ignores
the variable → derivation tests red. **Files:** `native_collaboration_runtime.py`, `session_delegation_control.py`,
`state_migration.py`, their tests.

### Task 2: Entry-point sweep and host entries

**Description:** One test module runs every entry point (runtime, adapters, retire CLIs, `relay_status.py`,
delegation controller `list`, migration `detect`, `scripts/acceptance/preflight.sh`, `cleanup.sh` preview) with
`AGENT_RELAY_HOME` set to a temp root and fake `HOME`, and asserts every reported path is under the temp root; a
source scan asserts no other module builds `.agent-relay` from the home directory. `install-claude` /
`install-codex` against fixture host configs write the resolved absolute paths under the temp root.

**Acceptance:** spec requirements 1 and 2. **Verify:** `validate.sh`. **Files:** new
`hooks/test_state_home.py`, any entry point that still hardcodes the root.

### Checkpoint (report): every entry point follows `AGENT_RELAY_HOME`

### Task 3: Seal the test run (D22)

**Description:** `validate.sh` creates a temp dir, exports `HOME`, `AGENT_RELAY_HOME`, `CLAUDE_CONFIG_DIR`,
`CODEX_HOME` under it for every test file, removes it afterwards (also on failure); a test asserts that inside the
run the default root is not the real one.

**Acceptance:** spec requirement 4. **Verify:** `validate.sh` output format unchanged; temp dir gone afterwards.
**Files:** `scripts/validate.sh`, `hooks/test_state_home.py`.

### Task 4: Docs

**Description:** README, `collaboration-ops` skill, interface §13 row and gap j: the variable, precedence, the
relative-path error, and that it does not move an already attached host entry.

**Acceptance:** spec requirement 5. **Verify:** `validate.sh`. **Files:** `README.md`,
`skills/collaboration-ops/SKILL.md`, `docs/collaboration-interface.md`.

### Task 5: Live moved-root check (round 1 owner told first)

**Description:** With `AGENT_RELAY_HOME` under the scratchpad: runtime `install`, `status`, `relay_status.py`,
then remove the temp root. Record the real `~/.agent-relay` listing and host config hashes before and after.

**Acceptance:** spec success criterion 2. **Files:** `tasks/test-isolation/todo.md`.

### Checkpoint (gate): module review
