# Plan: upgrade-codex-restart-check

Based on [`spec/upgrade-codex-restart-check.md`](../../spec/upgrade-codex-restart-check.md) (accepted by the user on
2026-10-16: assumption 5 of the 0.6.9 list, D196). Built after `codex-request-via-mailbox` on the same implementation
branch, as its own commit.

## Task List

### Task 1: the upgrade output
Red first in `hooks/test_runtime_upgrade.py`; green: `next` on an `upgraded` result.

### Task 2: the doctor check
Red first in `hooks/test_doctor.py` with injected process start, runtime root and clock; green: `codex-restart` in
`hooks/native_collaboration_doctor.py`, read only.

### Task 3: bookkeeping
README "升级运行时", CHANGELOG `[Unreleased]`.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH.

### Task 4: real check
`doctor` on this Mac (read only): the ChatGPT app started after the 0.6.8 upgrade, so `ok`.

### Task 5: PR and CI
One implementation PR for both modules; the four CI jobs green; tell the coordinator.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.9 release PR.
