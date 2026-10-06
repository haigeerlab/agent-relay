# Plan: acceptance-kit

Based on [`spec/acceptance-kit.md`](../../spec/acceptance-kit.md) (reviewed by the user on 2026-10-07, D8
accepted). Repository `/Users/vilin/Documents/haigeerlab/agent-relay`, branch `main`, local only. Reread
[`docs/collaboration-split-brief.md`](../../docs/collaboration-split-brief.md) after any context reset.

## Overview

First make the tests stand alone behind one entry (so every later module compares against a green start), then
write the checklist from the baseline and the interface document, then the two helpers.

## Architecture Decisions

- **Runner discovers tests by glob** (`plugins/agent-relay/hooks/test_*.py`), not by a list, so a test added by a
  later module cannot be forgotten; it prints each file's `Ran N` and a total, and fails on zero files found.
- **Checklist rows carry stable ids** (`A1`, `B3`, …) that records and the coverage table cite.
- **Helpers are read-only by default**; `cleanup.sh` writes only with `--confirm`, through the existing
  `native_collaboration_retire.py` entry (no new retire logic).
- **Fakes for host binaries** in helper tests (`claude`, `codex` on a temporary `PATH`), as in the extracted tests.
- Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: Test entry and standalone tests

**Description:** Write `scripts/validate.sh` per Spec requirement 1; apply D8 to
`test_native_only_collaboration.py` and `test_skill_entrypoints.py`; remove `test-collaboration-suite.sh` and
the assertions that read it.

**Acceptance:** 15 files, 201 tests, all pass; breaking one assertion on purpose makes the runner exit 1.

**Verify:** `/bin/bash scripts/validate.sh`; the deliberate-break check.

**Files:** `scripts/validate.sh`, `plugins/agent-relay/hooks/test_native_only_collaboration.py`,
`plugins/agent-relay/hooks/test_skill_entrypoints.py`, `plugins/agent-relay/hooks/test-collaboration-suite.sh`
(removed)

### Task 2: Checklist and record template

**Description:** Write `docs/acceptance/checklist.md` (sections A–E of Spec requirement 3, each item with id,
host pair, steps, expected current / target, evidence) and `docs/acceptance/record-template.md`. Add the
coverage table (baseline items 1–10, findings 1–7 → checklist ids) to todo.md.

**Acceptance:** every baseline item and finding is covered; every 【加固】 item names its hardening module.

**Verify:** the coverage table has no empty row; runner still green.

**Files:** `docs/acceptance/checklist.md`, `docs/acceptance/record-template.md`

### Checkpoint (report): tests stand alone, checklist covers the baseline

### Task 3: Preflight and cleanup helpers

**Description:** Write `scripts/acceptance/preflight.sh` and `scripts/acceptance/cleanup.sh` per Spec
requirements 5–6, and `plugins/agent-relay/hooks/test_acceptance_helpers.py` with fake host binaries: preflight
output fields and no writes; cleanup preview lists only the run prefix, refuses to retire without `--confirm`.

**Acceptance:** helper tests pass; the runner picks them up; preflight on this Mac prints real versions and
"not installed" for agent-relay.

**Verify:** `/bin/bash scripts/validate.sh`; one live `preflight.sh` run.

**Files:** `scripts/acceptance/preflight.sh`, `scripts/acceptance/cleanup.sh`,
`plugins/agent-relay/hooks/test_acceptance_helpers.py`

### Checkpoint (gate): module review

Stop and report per the brief format, including the comparison with the extracted suite (202 → 201 plus the
new helper tests). The repository is never pushed.

## Risks

- `native_collaboration_retire.py`'s arguments may not support selecting identities by prefix; if so, cleanup
  lists and retires one identity per call, still only within the prefix.
- The checklist will first be exercised after all translation modules; gaps found then return to this module.
