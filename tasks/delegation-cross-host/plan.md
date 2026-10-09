# Plan: delegation-cross-host

Based on [`spec/delegation-cross-host.md`](../../spec/delegation-cross-host.md) (accepted by the user on 2026-10-09:
assumptions 1–5, D158–D161). Branch `claude/delegation-cross-host` from main 9037f48. Fifth module of the round-2 batch
(0.6.0). Python only (hooks and skill); no bridge change expected.

## Task List

### Task 1: cross-host only, no host-native (D158, D159)
Red first: `authorize` rejects a target equal to the origin's host (`same-host-unsupported`) for both hosts; cross-host
passes; `host-native` is an unknown intent; an old row with `host-native` and a same-host target still loads, lists and
cancels; `continue` on it is refused. Then the store, the controller and the CLI choices; existing tests that relied on
same-host or `host-native` move to the new contract.

### Task 2: a clear answer when the state cannot be written (D160, controller part)
Red first: with a read-only state database, a state-writing controller command returns `state-not-writable`, a next
step and exit code 1, without a traceback.

### Task 3: skill, README, CHANGELOG (D160 skill part, D161)
session-delegation: same-host and `host-native` text out; Codex runs `create` / `continue` / `cancel` with the
sandbox escalation requested up front; the delegate plugin goes first in Claude Code. Skill tests; README; CHANGELOG.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14.

### Task 4: PR and CI
Push and open the PR; the four CI jobs green.

### Checkpoint (gate): module review
The user reviews and merges; the real-host acceptance (spec requirement 5) is run by the coordinator after the batch.
