# Plan: codex-not-loaded

Based on [`spec/codex-not-loaded.md`](../../spec/codex-not-loaded.md) (accepted by the user on 2026-10-16, D200). Branch
`claude/codex-not-loaded-impl` from main after this plan's PR; the round-2 coordinator is told every PR number; the
release PR waits until the implementation PR is merged.

## Task List

### Task 1: wake detail and presence
Red first (requirements 1–2) with a fake IPC socket. Green: `codex-wake.ts` maps a discovery timeout to the not-loaded
detail; `presence.ts` returns `not-loaded`; `PresenceState` gains it.

### Task 2: notice
Red first (requirement 3). Green: the Codex notice reason for a not-loaded ping.

### Task 3: docs and bookkeeping
`docs/BACKGROUND-WAKE.md`, `skills/collab`, `docs/collaboration-interface.md`, CHANGELOG `[Unreleased]`,
`UPSTREAM.md`, manifest.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Checkpoint (gate): module review
PR, CI green, the coordinator reviews, the user merges; then the 0.6.11 release PR.
