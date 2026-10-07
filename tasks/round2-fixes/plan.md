# Plan: round2-fixes

Based on [`spec/round2-fixes.md`](../../spec/round2-fixes.md) (accepted by the user on 2026-10-07: assumptions 1–4,
D49–D52). Branch `claude/round2-fixes` from main d56a68b. No bridge change expected. Red → green each task; every
`validate.sh` run's full output saved to the scratchpad.

## Task List

### Task 1: Read-only opens that work on SQLite 3.43 (D51)
Failing first: a WAL-mode database with no `-wal`/`-shm` beside it (the shape the backup API writes and a cleanly
closed mailbox leaves). `state_migration._read_only` is used only on private copies (snapshot, backup copy): open those
with a normal connection or `immutable=1`. `native_collaboration_runtime._mailbox_counts` reads a snapshot (as doctor
does), so the kept mailbox is not touched. Also check doctor's `_mailbox` and the other `mode=ro` openers
(`grep mode=ro`) for the same shape. Tests run under `/usr/bin/python3` 3.9.6 red before, green after.
**Files:** `hooks/state_migration.py`, `hooks/native_collaboration_runtime.py`, possibly
`hooks/native_collaboration_doctor.py`, `hooks/native_collaboration_retire.py`, tests.

### Task 2: Busy-timeout test that holds on every SQLite (D51)
Change the fixture so a writer's lock really blocks a reader on SQLite 3.37, 3.43 and the one in Python 3.14 (e.g. a
rollback-journal database with `BEGIN EXCLUSIVE`, or a WAL checkpoint lock — chosen by trying all three). Product code
unchanged unless the test shows a reader not waiting. **Files:** `hooks/test_mailbox_busy_timeout.py`.

### Checkpoint (report): validate green on 3.9.6, 3.10.7, 3.14.3
`scripts/validate.sh` with each interpreter first in PATH; outputs saved; counts recorded.

### Task 3: One node for every bridge start (D50)
New helper (e.g. `hooks/node_select.py`): `select_node(explicit, home, claude_json, codex_config)` → path and source
(`--node`, `claude-entry`, `codex-entry`, `PATH`), reading the `command` of the attached entries (Claude user entry;
Codex `[mcp_servers.agent_relay]`); `node_version(path)` runs `node --version` with a short timeout; below 22.5.0 or
unreadable → `node-too-old` / `node-unavailable` with path and version. Used by
`session_delegation_control._selected_backend` (refusal before any envelope or host process: tested by asserting no
store row and no fake-host call) for create, continue, status, cancel, permissions; and by `doctor`'s probe (default
`--node` no longer `node`; the probe check names the node and version). Tests with fake node scripts printing v12 and
v24.
**Files:** new helper, `hooks/session_delegation_control.py`, `hooks/native_collaboration_runtime.py`,
`hooks/native_collaboration_doctor.py`, tests.

### Task 4: Envelope and fallback for the result route (D49)
Envelope text: register first; if the mailbox tools are not listed, wait for them (ToolSearch by name allowed) and only
then answer; never answer only in the conversation. Check whether ToolSearch must be added to `--tools` (live probe in
Task 7 decides; the unit test pins whatever the list becomes). Fallback in `continue_turn`:
- `created`, host idle, registration missing → re-send the envelope once (resume with the same prompt and control
  block); a second miss → `held` `mailbox-registration-missing`, never `target-busy`.
- `running`, host `status=idle` with `state=working` and no result recorded (the C3 plain-repository case: registered
  in round 1, the resumed process answered before its bridge reconnected) → treated as an ended turn, so the follow-up
  is sent instead of held `target-busy`. This extends D49's wording ("idle and not registered") to the registered case
  seen in R2-6; accepted by the user at plan approval.
Tests with the existing fake host.
**Files:** `hooks/session_delegation_claude.py`, tests.

### Task 5: Deny rules stay while Claude sessions are open (D52, revised)
`uninstall-claude`: live Claude sessions (`~/.claude/sessions/<pid>.json` with a live pid, doctor's `_sessions` reader,
moved to a shared place) or running bridge servers of this runtime (`_servers_running(root)`); if either, remove the
entry, keep the seven rules, print "deny rules kept: N Claude session(s) still open; close every Claude session and run
uninstall-claude again from a terminal", followed by the exact command to copy (with the same `--root`,
`--claude-settings`, `--claude-json` the caller used). Otherwise as today. Tests: a fake live session alone, a fake running server
alone, neither.
**Files:** `hooks/native_collaboration_adapters.py`, `hooks/native_collaboration_doctor.py` (shared reader),
`hooks/test_host_backup.py`.

### Task 6: Docs
README: Python 3.9–3.14, Node 22.5+, the node used by the controller and doctor, D52 in §卸载 (the Claude deny-rule
step is the user's, in a terminal, with every Claude Code session closed); collaboration-ops skill: the agent no longer
runs that step in Claude, it hands the user the command; delegation skill text if it names `--node`; interface and checklist rows for R2-1, R2-6, R2-7, R2-9, R2-10.

### Task 7: Live (temporary `AGENT_RELAY_HOME` and HOME, coordinator told first)
- `doctor` and a controller create with nvm v12 first in PATH: refusal before any write; with the pinned node: ok.
- Migration (`detect`, `migrate --confirm`) and runtime `uninstall --confirm` + `install` with `/usr/bin/python3`.
- `uninstall-claude` in the temporary HOME with a live session record (a sleeping process's pid): rules kept; after
  it exits: removed. The R2-10 reproduction (real open session sees no worker tool) is the coordinator's re-run, or
  ours on real host files only with the user's agreement.
- D49 probe: a real background Claude target in a throwaway repository, quick task, several runs; record whether the
  result came back each time and whether ToolSearch was needed. The full C3 acceptance (3 runs plain + 3 worktree) is
  the coordinator's re-run.

### Checkpoint (gate): module review
