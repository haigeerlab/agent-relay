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

## Full run: the push of #51 to main

- Run 37888644735 (push, a200cd4), 05:27:17Z → 05:29:14Z: every job `scope=full: .github/workflows/ci.yml is not
  exempt`, 44 files / 652 tests, `validate: pass`.

## Skip runs: changes to exempt paths only (requirement 5)

- PR #52 (`tasks/ci-on-demand/todo.md`, `tasks/ci-on-demand/verification.md`), run 37888698062, 05:27:59Z → 05:29:05Z.
  Four required checks green, 7–9 s each. Every job: `scope=skip: all 2 changed paths are exempt`; checkout and
  Scope `success`; the two Python steps, `setup-node`, the toolchain check, `Bridge dependencies`, doctor and
  `Validate` all `skipped`; no `validate.sh` output in the log.
- The push of #52 to main (3df67ea), run 37889420017, 05:36:57Z → 05:37:14Z (17 s): the same `scope=skip` in every
  job, 7–8 s each.

## Reading the timings

- A job that skips takes 7–9 s instead of 56–91 s.
- The run as a whole took 17 s on the push but 66 s on PR #52: there the four jobs started one after another
  (05:28:09, 05:28:26, 05:28:43, 05:28:57) as macOS runners became free, so the wait for runners, not the jobs,
  set the time. Expect a skipping run to finish in roughly 15 s to 1 min, against about 2 min for a full one.
