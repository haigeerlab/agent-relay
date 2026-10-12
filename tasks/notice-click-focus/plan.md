# Plan: notice-click-focus

Based on [`spec/notice-click-focus.md`](../../spec/notice-click-focus.md) (accepted by the user on 2026-10-10:
assumptions 1–5, D190). Branch `claude/notice-click-focus` from main after this plan's PR. Only module of 0.6.4; the
round-2 coordinator is told every PR number.

## Task List

### Task 1: reproduce, then fix Terminal — **ask the user before each notice**
Reproduce on this Mac with the 0.6.3 script: two Terminal windows, the other one active, another app in front; click
the test notice and type — record where the input lands. Red first: `test/location.test.ts` expects the activating
statement after the tab selection. Green: `selectTab` for Terminal. Repeat the real check with the new script (built by
the worktree's code, as in #84): input lands in the target window; the one-window, two-tab case still works.

### Task 2: iTerm with several windows
The same real check for iTerm with the 0.6.3 script. If the target window does not become active: red test, then the
fix, then the check again. If it does: record it and change nothing.

### Task 3: is the place visible in the banner?
Show one approval test notice whose subtitle is as long as the coordinator's (70+ characters, place last) and ask the
user what the banner shows. Cut off → red tests, then the place moves to the front of the subtitle for both notice
kinds. Visible → no change, recorded.

### Task 4: bridge bookkeeping
`UPSTREAM.md`, `python3 -B scripts/bridge-manifest.py`, CHANGELOG `[Unreleased]` (needs `upgrade --confirm`), README
only if the subtitle order changed — in the same commit as the last bridge change (D24).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 5: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.4 release PR.
