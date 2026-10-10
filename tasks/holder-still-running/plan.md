# Plan: holder-still-running

Based on [`spec/holder-still-running.md`](../../spec/holder-still-running.md) (accepted by the user on 2026-10-10:
assumptions 1–8, D187). Branch `claude/holder-still-running` from main after this plan's PR. Third and last module of
0.6.2; the release PR waits for it. The round-2 coordinator is told every PR number.

## Task List

### Task 1: takeover refuses a running Claude holder (D187)
Red first in `bridge/test/identity.test.ts` (requirement 1's seven cases; the registry fixture comes from the presence
tests' helper, moved to a shared test helper only if it has to be). Green: in `server.ts` `bridge_register`, before any
write, when `takeover` resolves an owner or binding conflict, read `claudeSessionsOrNull()` once and classify each
conflicting holder: Claude and listed → throw `holder-still-running: …`; Claude and registry `null` → note "could not
confirm"; Codex → note "cannot confirm". The `takeover` parameter's description gains one sentence. `UPSTREAM.md` row,
`python3 -B scripts/bridge-manifest.py`, CHANGELOG `[Unreleased]` (takes effect after `upgrade --confirm`), one sentence in
the collab skill with its guard test — all in the same commit as the bridge change (D24).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`. No live check
on the user's runtime: the installed bridge changes only with the 0.6.2 upgrade.

### Task 2: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.2 release PR (it also carries nothing else pending: #77's two low
items are already in the install-truth closeout).
