# Plan: orchestrator-removal

Based on [`spec/orchestrator-removal.md`](../../spec/orchestrator-removal.md) (accepted by the user on 2026-10-08:
assumptions 1–8, D90–D94). Branch `claude/orchestrator-removal` from main 180de7b. Red → green, one commit per task.
First module of 0.5.0; no release at its end.

Order: the bridge first (the probe can only demand ten tools once the server serves ten), then the Python side, then
docs, then the live upgrade. Each task leaves the repo green.

## Task List

### Task 1: the bridge serves exactly ten tools (D90, D91, D93)
Red first: `mcp-integration.test.ts` lists the tools and expects exactly `MAILBOX_TOOLS`' ten; a schema test opens a
v5 mailbox holding orchestration rows and finds them intact (green already; it guards D93). Then: drop the six tools,
`bridge_retire` and the "Codex workers" paragraph from `server.ts`; delete `orchestrator.ts`, `simple-tools.ts`,
`process-info.ts`, `orchestration.test.ts`, `simple-tools.test.ts`; adjust `mcp-integration.test.ts` cases that used
the removed tools.
Files: `src/server.ts`, the deleted files, `test/mcp-integration.test.ts`, `test/schema.test.ts`; `UPSTREAM.md`,
manifest, CHANGELOG.

### Task 2: no orchestrator left in the store, housekeeping and CLI (assumption 2)
Remove the run types and nine methods from `BridgeStore` and the run count from its report; `Housekeeper` without the
orchestrator, reconcile and run-file pruning; `diagnostics.ts` without run counts; `cli.ts` `REQUIRED_TOOLS` (mailbox
tools only), the `resolveCodexBinary` import, the runs directory in the permission sweep, doctor's "Codex runs",
`status`'s runs line, help text; `paths.ts` without `runsDir` / `worktreeRoot`; `scripts/smoke-orchestrator.ts` and
`docs/AUTONOMOUS-ORCHESTRATOR-DESIGN.md` deleted. Tests that asserted those outputs updated.
Verify: `npm run check`; `grep -rn "orchestrat\|simple-tools\|process-info\|runsDir\|worktreeRoot" src scripts test`
finds nothing but the schema migrations and the D93 schema test. `UPSTREAM.md`, manifest, CHANGELOG.

### Checkpoint (report): bridge `npm run check`, validate on one Python

### Task 3: probe, install, uninstall, doctor (D91, D92)
Tests first: the probe fails on an eleventh tool and on a missing one; install writes no Claude deny rules for the
legacy names; uninstall of a Claude config with the old deny rules and of a Codex config with their approval
sub-tables removes them all; doctor is ok on a fresh install and on a host still carrying the old rules. Then
`DENIED_TOOLS` → `LEGACY_WORKER_TOOLS` (removal only) in `native_collaboration_runtime.py`,
`native_collaboration_adapters.py`, `native_collaboration_doctor.py` and their tests.

### Task 4: docs (D94)
Every mention of the removed tools, "Codex workers" or `bridge_retire`: `bridge/README.md`, `bridge/INSTRUCTIONS.md`,
`bridge/CHANGELOG.md` (an entry, history kept), `docs/collaboration-interface.md` (server tool list; "were removed in
0.5.0, tag `v0.4.0` has them"), collab and session-delegation skills, agent-relay README, CHANGELOG `[Unreleased]`.
Verify: `grep -rn` over docs, skills and README finds the names only in history and the removal note.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 5: live upgrade from v0.4.0 and uninstall
In a `mktemp -d` HOME: install the v0.4.0 runtime and both hosts; write messages, acknowledgements and one
orchestration row; upgrade to this branch's runtime; schema 5, every row intact, `doctor` all ok, `tools/list` the ten;
uninstall removes the old Claude deny rules and Codex approval sub-tables. Temporary HOME to the Trash.

### Checkpoint (gate): module review
Then push and PR with the user's approval; CI green on all jobs; tell the round-2 coordinator.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A test or helper still imports a removed module | Medium | `tsc` in `npm run check`, plus the grep in Task 2 |
| A 0.4.0 host keeps stale rules or approval tables | Medium | Task 3 tests and Task 5 live uninstall |
| Removing run methods breaks opening an old mailbox | Medium | D93 schema test in Task 1; Task 5 upgrade with a real orchestration row |
| Manifest out of date | Low | Updated in Tasks 1 and 2; the runtime install check runs in validate |
