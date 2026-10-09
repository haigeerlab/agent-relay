# Plan: wake-any-mode

Based on [`spec/wake-any-mode.md`](../../spec/wake-any-mode.md) (accepted by the user on 2026-10-09: assumptions 1–5,
D140–D145). Branch `claude/wake-any-mode` from main 09b317a. First module of the round-2 batch released together as
0.6.0 (interface 2.0); the round-2 coordinator runs the real-project acceptance after the batch.

## Task List

### Task 1: the bridge stops overriding woken Codex turns (D140, D141)
Red first in `bridge/test`: `codexTurn` request is exactly `{threadId, input: []}` with the `untrusted_input` call kept;
`wakeCodex` has no gate argument and no version/gate `held`; the dispatcher ignores a pre-existing `codex-gate.off`,
writes none and sends no `gate-off` notice. Then delete `codex-gate.ts` and its test, and remove its users
(`wake-dispatcher.ts`, `notify.ts`, `wake-queue.ts`, `server.ts` comment, test support).

### Task 2: doctor and interface (D144, D145)
Red first in `test_doctor.py`: `codex-approval` is `ok` with the "own settings" detail, says an existing
`codex-gate.off` is unused and may be deleted, and gives no version-threshold warning. Then `native_collaboration_doctor.py`,
the D70 comment in `native_collaboration_adapters.py`, `interface.json` 2.0 and `relay_status.py`'s history note;
update any test that pinned 1.4.

### Task 3: skills, README and CHANGELOG (D142, D143, D144)
collab: bind in any permission mode, the woken session's own settings govern it, the floor and the risk; drop the gate
and `codex-gate.off` text. collaboration-ops: drop the gate paragraph, mention the obsolete file. README: same, plus the
risk. CHANGELOG `[Unreleased]`.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14 with the bridge check.

### Task 4: PR and CI
Push and open the PR with the user's approval; the four CI jobs green.

### Checkpoint (gate): module review
The user reviews and merges; the real-host acceptance (spec requirement 6) is run by the coordinator after the batch.
