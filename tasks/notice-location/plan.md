# Plan: notice-location

Based on [`spec/notice-location.md`](../../spec/notice-location.md) (accepted by the user on 2026-10-10: assumptions
1–5, D188). Branch `claude/notice-location` from main after this plan's PR. First module of 0.6.3; the round-2
coordinator is told every PR number.

## Task List

### Task 1: where a session is (pure, tested)
Red first: the registry reader keeps `entrypoint`, `kind`, `hostSessionId`; `locate(...)` returns one of desktop,
terminal (with tty and the owning app's bundle id when the parent walk finds an `.app`), background, codex, unknown;
tty and pid formats are checked. Green: a small `location.ts`; the parent walk uses `/bin/ps -o ppid=,comm=` with a
bounded depth and timeout.

### Task 2: the text says where
Red first: `noticeFields` for both notice kinds and each place, with and without preview, within today's length
limits; the osascript fallback gets the same fields. Green: `notify.ts` takes an optional location.

### Task 3: the click goes there
Red first: argv per place — `-activate <fixed bundle id>` for desktop, Codex and unknown terminal apps; `-execute` with
the fixed Terminal / iTerm AppleScript carrying only the tty; nothing for background or unknown; hostile names, paths,
bodies and senders never outside `-title`, `-subtitle` and stdin. Green: `notify.ts` appends the action; both callers
pass the location (approval notices: the waiting Claude session; Codex notices: the Codex app).

### Task 4: real checks on this Mac — **ask the user before each** (they show notices and move windows)
Approval notice from a desktop session and from a Terminal tab (iTerm if installed): text and click; a Codex notice;
then, separately consented, one try each of a `claude://` and a `codex://` deep link. A deep link that does not open the
exact session is not used. Results in the todo.

### Task 5: docs and bridge bookkeeping
`UPSTREAM.md`, `python3 -B scripts/bridge-manifest.py`, CHANGELOG `[Unreleased]` (needs `upgrade --confirm`), README
"授权与安全" two sentences with a guard test — in the same commit as the last bridge change (D24).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 6: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then `delegation-status-read-only`.
