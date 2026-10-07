# Plan: identity-check

Based on [`spec/identity-check.md`](../../spec/identity-check.md) (accepted by the user on 2026-10-07: schema v5,
D37–D40, unreadable Codex config fails closed). Branch `claude/identity-check` from main 6450d92. Every bridge change
updates `UPSTREAM.md` and `UPSTREAM.sha256` (`scripts/bridge-manifest.py`) in the same commit; red → green each task.

## Task List

### Task 1: busy_timeout first (D40) — own commit
`BridgeStore` sets `busy_timeout` before `journal_mode` and every other statement. Regression test across processes:
one process holds `BEGIN IMMEDIATE`, another opens the mailbox and reads and writes, the first releases within the
timeout → the second succeeds (red today: "database is locked"). Python readers pass an explicit `timeout=5`.
**Files:** `src/bridge-store.ts`, a new or existing TS test, `hooks/native_collaboration_retire.py`,
`hooks/session_delegation_backend.py`.

### Task 2: Schema v5 and recorded host (assumption 3)
v5 adds nullable `agents.host_app`, `agents.host_session` (+ a flag that the Codex value is claimed, e.g. host_app
`codex` always unverified); `register()` records them; Python `MAILBOX_SCHEMA_VERSIONS = (2, 3, 4, 5)`; v2 → v5 in one
open with backup; older-process inserts still work. **Files:** `src/schema.ts`, `src/bridge-store.ts`,
`test/schema.test.ts`, `hooks/native_collaboration_runtime.py`, Python tests.

### Task 3: Sender check (assumption 2, D37, D39)
A per-process set of proven names (registered here) plus the recorded Claude host = this process's session; checked
in `bridge_send` (`from`), `bridge_ack` (`agent`) and `bridge_wait` with `acknowledge: true`; refusal text per D39.
Bridge notices, CLI and Python hooks unaffected; existing MCP tests that send without registering are adjusted
(recorded). Tests at MCP level with two server processes on one file (different `CLAUDE_CODE_SESSION_ID`, and one
without, as Codex). **Files:** new `src/identity.ts`, `src/server.ts`, new `test/identity.test.ts`.

### Checkpoint (report): open order, schema and sender check green

### Task 4: Takeover (assumption 4)
`bridge_register` gains `takeover?: boolean`; a name whose recorded host differs from the caller's known host is
refused without it (says whether the recorded Claude session is running); the silent move from a dead Claude session
is removed; NULL-owner names are claimed; a Claude caller may bind only its own session. Tests per spec req 3.

### Task 5: Reply rule (assumption 5)
`replyTo` send must come from the original's recipient; broadcast: anyone but its sender; replies to `bridge` notices
refused. Tests.

### Task 6: Codex auto-approval (assumption 6, D38)
`codexAutoApproved(env)` reads `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`) top-level
`approvals_reviewer` / `approval_policy`; unreadable or malformed → treated as auto-approved. Binding a Codex session
refused; a Codex ping is `held` with the reason (binding kept). Tests with fixture `CODEX_HOME`s: guardian, never,
on-request, missing, unreadable, malformed. **Files:** new `src/codex-approval.ts`, `src/server.ts`,
`src/wake-dispatcher.ts` (or the Codex adapter).

### Task 7: Docs
README; `collab` skill (takeover only after the user agrees; guardian blocks Codex wake; re-register after a restart);
`collaboration-ops`; interface rows 44, 45, 77, 79, 88, 126–129, 136, gap g, finding 1; checklist A2, B7, B8;
`UPSTREAM.md`.

### Task 8: Live (temporary `AGENT_RELAY_HOME`, coordinator told first)
Runtime from this branch on a v2 mailbox (`upgrade --confirm`, first open → v5). Two bridge servers with different
`CLAUDE_CODE_SESSION_ID` and one without: sender check, takeover, B8 (reply as non-recipient refused); B7 with fixture
`CODEX_HOME` (guardian → bind refused, ping held). Real `~/.codex/config.toml` only read. No host config change.

### Checkpoint (gate): module review
