# Plan: ci-on-demand

Based on [`spec/ci-on-demand.md`](../../spec/ci-on-demand.md) (accepted by the user on 2026-10-09: assumptions 1–6,
D135–D139). Branch `claude/ci-on-demand` from main 1d05bff. The user merges after every CI check has finished green.

## Task List

### Task 1: the scope decision (D135)
Red first, `hooks/test_ci_scope.py` (requirement 1), then `scripts/ci_scope.py`: stdlib only; reads the event, base and
head from environment variables, lists the changed paths with `git diff --name-only`, prints `scope=full|skip` and the
reason, and writes `scope=…` to `$GITHUB_OUTPUT` when set. The exempt globs are a constant in this file.

### Task 2: the guard (D137)
Red first: the guard test, run by `validate.sh`, scans what `validate.sh` runs (Python tests and hooks, `scripts/`, the
bridge's `src/` and `test/`) for references to the exempt paths; a planted `spec/` reference makes it fail, and the
current tree passes.

### Task 3: the workflow, README and CHANGELOG (D136, D138, D139)
Red first, extend `test_ci_workflow.py` (schedule `0 3 * * 1`; a `scope` step running `scripts/ci_scope.py`; `npm ci`,
doctor and `validate.sh` conditioned on `full`; every existing assertion kept). Then `ci.yml`: checkout with full
history, the scope step after checkout, the conditions, the schedule. README "开发与 CI"; CHANGELOG `[Unreleased]`.

### Checkpoint (report): local validation
`scripts/validate.sh` green here; `ci_scope.py` dry-run against real commits of this repository (an exempt-only range
gives `skip`, a range touching code gives `full`).

### Task 4: the module's PR runs full (requirement 4)
Push and open the PR with the user's approval; all four jobs green with `scope=full` in the log.

### Task 5: real `skip` evidence (requirement 5)
After the module PR is merged: a follow-up PR touching only `tasks/ci-on-demand/` (this todo and
`verification.md`) shows the four required checks green with the `skip` reason and no `Validate` step; timings
recorded in `verification.md`.

### Checkpoint (gate): module review
The user reviews the evidence and merges the follow-up PR.
