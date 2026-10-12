# Plan: notice-click-live-tab

Based on [`spec/notice-click-live-tab.md`](../../spec/notice-click-live-tab.md) (accepted by the user on 2026-10-12:
assumptions 1–5, D191; iTerm unchanged). Branch `claude/notice-click-live-tab-impl` from main after this plan's PR.
Only module of 0.6.5; the round-2 coordinator is told every PR number. The release PR is opened only after the
implementation PR is merged.

## Task List

### Task 1: red test, then the Terminal match
Red first: `test/location.test.ts` expects the Terminal match line
`if tty of t is "/dev/<tty>" and (count of processes of t) > 0 then` and the iTerm script exactly as in 0.6.4.
Green: the one line in `selectTab`. Existing assertions stay.

### Task 2: real check with the kept scene — **ask the user before each notice**
Scene: Terminal window 316414 (ended, reports the target's tty) and the live session's window. Read-only query first
to confirm the duplicate tty still shows. The test notice is built by the worktree's code; the user clicks the banner;
I read the windows (`is_main`, `is_minimized`) before and after.
- Target minimized → restored and active; 316414 untouched.
- Target not minimized, another window active → the target becomes the active window; 316414 untouched.
If the scene is gone (a window was closed), rebuild it only with steps the user agrees to, or record what could not be
checked.

### Task 3: bridge bookkeeping
`UPSTREAM.md`, `python3 -B scripts/bridge-manifest.py`, CHANGELOG `[Unreleased]` (needs `upgrade --confirm`; known
issue: an ended iTerm session kept open by the user's profile setting is not measured) — in the same commit as the
bridge change (D24). README unchanged.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 4: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.5 release PR.
