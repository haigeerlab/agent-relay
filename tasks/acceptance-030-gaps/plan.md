# Plan: acceptance-030-gaps

Based on [`spec/acceptance-030-gaps.md`](../../spec/acceptance-030-gaps.md) (accepted by the user on 2026-10-08:
assumptions 1–7, D72–D74). Branch `claude/unbound-recipient-warning` from main 631fa84. Red → green, one commit per
task.

## Task List

### Task 1: Warn when the recipient has no wake binding and no known host (D72)
Bridge test first (`test/notify.test.ts`, beside the D67 send-time test): a recipient registered from a Codex caller with
`wake: null` (no host) gets the D72 warning on `bridge_send`, and nothing is written to `AGENT_RELAY_NOTIFY_LOG`;
`wake: false`, a broadcast and a duplicate stay silent; a recipient with a recorded Claude host and no binding gets no
D72 warning. Red, then `server.ts` `bridge_send`. `UPSTREAM.md` row, `UPSTREAM.sha256` regenerated, CHANGELOG
`[Unreleased]` entry.
**Files:** `bridge/src/server.ts`, `bridge/test/notify.test.ts`, `bridge/UPSTREAM.md`, `bridge/UPSTREAM.sha256`,
`CHANGELOG.md`.

### Task 2: Same-second upgrade picks a suffixed stamp (D74)
Python test first (`hooks/test_runtime_upgrade.py`): with `backups/<stamp>/` already present for the frozen current
second, `upgrade --confirm` succeeds with backup, previous and stage all named `<stamp>-1`; all 100 names taken →
refused. Red, then `upgrade_runtime` (failed-upgrade directory uses the same suffix). CHANGELOG entry.
**Files:** `hooks/native_collaboration_runtime.py`, `hooks/test_runtime_upgrade.py`, `CHANGELOG.md`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 3: Live check in a temporary AGENT_RELAY_HOME/HOME, then the README paragraph (D73)
Install the runtime from this tree into a short temporary home; register a Codex-style identity with `wake: null` and
send to it from another identity: the D72 warning appears, no notice is shown. Run `install-codex
--approve-mailbox-tools` and `upgrade --confirm` within one second: the upgrade succeeds into `<stamp>-1`. Check
assumption 5 (which app macOS attributes `osascript` notifications to) on this Mac; then write the README paragraph next
to `notify.off` with what was observed. Evidence in the todo; temporary home moved to the Trash afterwards.
**Files:** `README.md`, `CHANGELOG.md`, `tasks/acceptance-030-gaps/todo.md`.

### Checkpoint (gate): module review
