# Plan: codex-request-via-mailbox

Based on [`spec/codex-request-via-mailbox.md`](../../spec/codex-request-via-mailbox.md) (accepted by the user on
2026-10-16: assumptions 1–7, option A, D195). Branch `claude/codex-mailbox-impl` from main after this plan's PR. First
module of 0.6.9; `upgrade-codex-restart-check` follows on the same implementation branch as a separate commit; the
round-2 coordinator is told every PR number; the release PR waits until the implementation PR is merged.

## Task List

### Task 1: the selector
Red first in `hooks/test_session_routing.py` (requirement 1). Green in `hooks/session_routing.py`: optional fact
`exchange` (`ask`, `assign`, `unknown`); the Codex/Codex rule before the native branch; the `nextStep` sentence when
the pair cannot use the mailbox.

### Task 2: the skills and the interface document
Red first (requirement 2). Green: `skills/session-routing/SKILL.md` (when to pass which value; on
`codex-work-via-mailbox` send with `bridge_send`, answer with `replyTo`), one line in `skills/collab/SKILL.md`,
`docs/collaboration-interface.md` selector and Codex ↔ Codex rows.

### Task 3: bookkeeping
CHANGELOG `[Unreleased]` (plugin update only).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH.

### Checkpoint (gate): module review
Together with `upgrade-codex-restart-check` in one implementation PR; the coordinator reviews; the user merges.
