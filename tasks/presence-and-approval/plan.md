# Plan: presence-and-approval

Based on [`spec/presence-and-approval.md`](../../spec/presence-and-approval.md) (accepted by the user on 2026-10-09:
assumptions 1–5, D146–D149). Branch `claude/presence-and-approval` from main d32f861. Second module of the round-2
batch (0.6.0).

## Task List

### Task 1: presence reading and the directory (D146)
Red first (bridge): `claudeSessions()` also reads `status`, `statusUpdatedAt`, `waitingFor`; a new `presence.ts` maps a
Claude host to running / waiting-approval / waiting-input / stopped / unknown and a Codex host (fake IPC owner reply)
to running / stopped / unknown; `bridge_agents` returns `presence` per agent.

### Task 2: the sender is told (D147)
Red first: `bridge_send` to a `waiting-approval` or `stopped` recipient carries the warning; a running one does not.

### Task 3: the approval notice (D148)
Red first: the dispatcher, at most every 30 s, checks Claude recipients of unacknowledged direct messages; a
`waiting-approval` one gets one macOS notice per waiting episode (session id + `statusUpdatedAt`), none after the
message is acknowledged, none with notices off, a new one for a new episode; the text names the session and the sender.

### Task 4: doctor shares the reading (D149)
Red first in `test_doctor.py`: `wake-bindings` uses the same states and words as the directory.

### Task 5: skill, README, CHANGELOG, bridge records
collab directory format with the presence words; README; CHANGELOG `[Unreleased]`; `UPSTREAM.md` row and
`scripts/bridge-manifest.py` in the same commit as the bridge change.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14.

### Task 6: PR and CI
Push and open the PR; the four CI jobs green.

### Checkpoint (gate): module review
The user reviews and merges; the real-host acceptance (spec requirement 6) is run by the coordinator after the batch.
