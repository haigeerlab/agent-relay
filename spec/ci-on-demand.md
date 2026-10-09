# Spec: ci-on-demand

## Objective

Every pull request and every push to `main` runs the full ci-macos matrix (D80, D80a): four macOS jobs, each running
all of `scripts/validate.sh`. A change that only touches process and record files (this repository's agent
instructions, specs, plans and spec-guard state) cannot break anything those jobs check, yet the user waits about two
minutes for it before merging; PR #50 (two agent-instruction files) was one. The user asked (2026-10-09) to let such
changes pass quickly, to guard the list of files that may skip, and to run the full matrix once a week so a runner image
that moves under us is found without waiting for the next code PR.

Readers: the user, who merges; reviewers of every later PR.

## What exists today (main 1d05bff, 2026-10-09)

- `.github/workflows/ci.yml`: `pull_request`, `push` to `main`, `workflow_dispatch`; no path filter. One job matrix
  `Python {3.9, 3.14} / Node {22, 24}` on `macos-15`, all four in parallel: checkout, Python, Node, `npm ci` in the
  bridge, doctor `toolchain`, then `bash scripts/validate.sh` with a check that the bridge suite ran.
- `main` branch protection requires the four checks by name (`Python 3.9 / Node 22`, … `Python 3.14 / Node 24`),
  non-strict. Set by the user after ci-macos (D82).
- Measured on recent runs: each job 56–80 s, of which `Validate` is about 90%; a PR run takes about 2 min from start to
  finish, the rest being runner start-up. Locally the full `validate.sh` takes about 60 s, the bridge's `npm run check`
  about 10 s of it.
- 17 of the 42 Python test files run `node`, so the Python and Node axes cannot be tested separately; this module keeps
  the full 2 × 2 whenever tests run.
- Tests read some Markdown: root `README.md`, `SKILL.md` files, `plugins/agent-relay/references/*.md`, a decision
  record under `docs/history/`, the bridge's `UPSTREAM.md`. None reads `CLAUDE.md`, `AGENTS.md`, `spec/`, `tasks/` or
  `.agent/`, and no test walks the whole repository.
- `hooks/test_ci_workflow.py` asserts the triggers, least privilege, SHA pins, the full matrix on `macos-15`, and that
  the bridge check cannot be skipped.

## Assumptions (accepted by the user 2026-10-09)

1. The aim is the user's waiting time, not cost: the repository is public and its macOS minutes are free.
2. When tests run, they run as today: the full 2 × 2 of D80a. This module adds no partial matrix.
3. The exempt paths are exactly: `CLAUDE.md`, `AGENTS.md`, `spec/**`, `tasks/**`, `.agent/**`. `docs/**`,
   `README.md`, `CHANGELOG.md` and every Markdown file under `plugins/` stay checked.
4. Branch protection is not touched: the same four required checks, by the same names, report on every PR.
5. The weekly run is Monday 03:00 UTC (11:00 Beijing time), on `main`; a failure is reported by GitHub's normal
   notification for scheduled workflows. Nothing else is added (no issue filing, no messages).
6. No version bump: CI is not an interface change (interface stays 1.4).

## Decisions

- **D135 scope rule.** A run is `skip` only when it is a `pull_request` or a `push` to `main` and every changed path is
  exempt (assumption 3). Everything else is `full`: `schedule`, `workflow_dispatch`, a push whose `before` is unknown
  (all zeros) or unreachable, an empty or unreadable change list, and any change list with one non-exempt path.
  When in doubt the answer is `full`.
- **D136 skip inside the job, not a path filter.** The workflow keeps triggering on every PR and push. Each matrix job
  checks out, decides the scope, and in `skip` mode skips every later step after printing why, so the four required
  checks still report
  (as success) under their names. A workflow-level `paths-ignore` is not used: it would leave a docs-only PR waiting on
  four checks that never report. The decision is made by a small stdlib Python script, `scripts/ci_scope.py`, given the
  event and the base and head commits through environment variables (never interpolated into shell), which reads the
  change list from `git diff --name-only` and prints the scope and the reason.
- **D137 the exempt list is guarded.** The exempt globs live in one place (`scripts/ci_scope.py`). A test fails if
  anything `validate.sh` runs refers to an exempt path: the Python tests and hooks, `scripts/`, and the bridge's
  sources and tests. The check is a static scan for those paths as path literals (for example `"spec"` as a path part,
  `spec/`, `tasks/`, `CLAUDE.md`, `AGENTS.md`, `.agent/` but not `.agent-relay`); it errs toward failing, and a failure
  means the path must leave the exempt list or the reference must go.
- **D138 weekly full run.** `schedule: cron '0 3 * * 1'` added to the triggers; scheduled runs are always `full`
  (D135).
- **D139 D80 and D80a stand.** Triggers, least privilege, SHA pins, `macos-15`, the 2 × 2 matrix and the bridge check
  are unchanged; this module only adds the scope step, the schedule, and the conditions that make the existing steps
  run in `full` mode only.

## Requirements

1. Red first, `hooks/test_ci_scope.py`: `ci_scope.py` returns `skip` for a change list made only of exempt paths, and
   `full` for: one non-exempt path among exempt ones; look-alikes (`spec.md`, `specs/x`, `.agent-relay/x`,
   `docs/CLAUDE.md`, `tasks.md`); an empty list; `schedule` and `workflow_dispatch`; a push with an all-zeros `before`;
   a base it cannot diff against. The reason it prints names the first non-exempt path, or the event.
2. Red first, the guard of D137, run by `validate.sh`; a deliberately planted reference to `spec/` makes it fail.
3. `ci.yml` per D136/D138: checkout with enough history to diff the PR base or the push's `before`; a `scope` step;
   every later step runs unless the scope is `skip` (`!= 'skip'`, so a missing output runs the tests: amended while
   building, 2026-10-09); the `schedule` trigger. `test_ci_workflow.py` is extended to
   assert the schedule, the scope step, and that `validate.sh` and `npm ci` are conditioned on `full`, and keeps every
   existing assertion.
4. This module's own PR changes `ci.yml` and scripts, so its CI must run `full` and be green in all four jobs.
5. Evidence of `skip` from real CI: the module's closing commit touches only `tasks/` and `spec/`; its PR (or a
   follow-up PR with only exempt changes) shows the four required checks green with the `skip` reason in the log and
   no `Validate` step run. Recorded in `tasks/ci-on-demand/verification.md`.
6. README "开发与 CI": which changes skip the tests, that the weekly run exists, and how to force a full run (manual
   `workflow_dispatch`). CHANGELOG `[Unreleased]`.
7. Local validation unchanged: `scripts/validate.sh` green here.

## Boundaries

- Always: decide `full` when in doubt; keep the four check names; pass event data through environment variables.
- Ask first: branch protection or any repository setting; adding a path to the exempt list; any partial matrix.
- Never: a workflow-level path filter on `pull_request`; `pull_request_target`; secrets; skipping on `schedule` or
  `workflow_dispatch`.

## Success criteria

A PR that changes only exempt paths shows the four required checks green without running the tests, in well under
the current two minutes; any other PR runs the full matrix as before; a reference to an exempt path from anything the
tests run turns CI red; the weekly scheduled run exists and runs the full matrix.

## Open questions

None. Accepted by the user on 2026-10-09 (assumptions 1–6, D135–D139).
