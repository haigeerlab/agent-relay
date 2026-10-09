# Verification: ci-on-demand

Evidence for [`spec/ci-on-demand.md`](../../spec/ci-on-demand.md), requirements 4 and 5, from real GitHub Actions runs.

## Before (main 1d05bff and earlier, full matrix on every change)

- PR #50 (`CLAUDE.md`, `AGENTS.md` only), run 37885300732: four jobs ran the whole of `validate.sh`; each job about
  1 min, the run about 2 min.

## Full run: the module's own PR (requirement 4)

- PR #51, run 37888155537, 2026-10-09T05:21:02Z → 05:22:41Z (1 min 39 s). Four required checks green, 1m12s–1m31s each.
- Scope step in every job: `scope=full: .github/workflows/ci.yml is not exempt`.
- Each job: 44 files / 652 tests, "ok    bridge: npm run check 155", `validate: pass`.
- New steps' cost: checkout with `fetch-depth: 0` 2–3 s, Scope 0–1 s.

## Skip run: a PR that changes only exempt paths (requirement 5)

- This PR (only `tasks/ci-on-demand/`): to be recorded from its run.
