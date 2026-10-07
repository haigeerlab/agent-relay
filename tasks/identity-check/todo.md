# Todo: identity-check

- [x] Task 1: busy_timeout first (D40) — own commit. `BridgeStore` runs `busy_timeout = 5000` before `journal_mode` and `foreign_keys` (`diagnostics.ts` already set it first). New `test/open-lock.test.ts`: a child process takes `locking_mode = EXCLUSIVE; BEGIN EXCLUSIVE` and holds it 800 ms; the store opens, reads and writes, having waited ≥ 500 ms — red before ("database is locked" at open), green after. Python: `MAILBOX_BUSY_TIMEOUT = 5.0` in `native_collaboration_runtime.py`, passed explicitly by `native_collaboration_retire._open_read_only` and both `session_delegation_backend` connections; new `test_mailbox_busy_timeout.py` (2 tests) holds an exclusive lock 0.6 s and both readers wait and read. Those Python tests pin today's behaviour (Python's default timeout is already 5 s), so they are green before and after by design
- [x] Task 2: Schema v5 and recorded host (assumption 3) — v5 adds nullable `agents.host_app`, `agents.host_session`; `BridgeAgent.host` (`{app, sessionId}` or null); `register(name, capabilities, host?)` records a given host and keeps the recorded one otherwise (COALESCE). Tests (red before): v2 → v5 in one open with one `bridge-pre-v5-from-v2-*` backup, rows intact, new columns nullable; older-process agent insert reads `host: null`; record / keep / replace. Python `MAILBOX_SCHEMA_VERSIONS = (2, 3, 4, 5)`, retire and delegation-backend read v3–v5 and refuse v6. Who may set or change the host is Tasks 3–4. TS 121, validate 424
- [ ] Task 3: Sender check (assumption 2, D37, D39)
- [ ] Checkpoint (report): open order, schema and sender check green
- [ ] Task 4: Takeover (assumption 4)
- [ ] Task 5: Reply rule (assumption 5)
- [ ] Task 6: Codex auto-approval (assumption 6, D38)
- [ ] Task 7: Docs
- [ ] Task 8: Live (temporary `AGENT_RELAY_HOME`, coordinator told first)
- [ ] Checkpoint (gate): module review
