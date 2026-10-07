# Todo: identity-check

- [x] Task 1: busy_timeout first (D40) — own commit. `BridgeStore` runs `busy_timeout = 5000` before `journal_mode` and `foreign_keys` (`diagnostics.ts` already set it first). New `test/open-lock.test.ts`: a child process takes `locking_mode = EXCLUSIVE; BEGIN EXCLUSIVE` and holds it 800 ms; the store opens, reads and writes, having waited ≥ 500 ms — red before ("database is locked" at open), green after. Python: `MAILBOX_BUSY_TIMEOUT = 5.0` in `native_collaboration_runtime.py`, passed explicitly by `native_collaboration_retire._open_read_only` and both `session_delegation_backend` connections; new `test_mailbox_busy_timeout.py` (2 tests) holds an exclusive lock 0.6 s and both readers wait and read. Those Python tests pin today's behaviour (Python's default timeout is already 5 s), so they are green before and after by design
- [ ] Task 2: Schema v5 and recorded host (assumption 3)
- [ ] Task 3: Sender check (assumption 2, D37, D39)
- [ ] Checkpoint (report): open order, schema and sender check green
- [ ] Task 4: Takeover (assumption 4)
- [ ] Task 5: Reply rule (assumption 5)
- [ ] Task 6: Codex auto-approval (assumption 6, D38)
- [ ] Task 7: Docs
- [ ] Task 8: Live (temporary `AGENT_RELAY_HOME`, coordinator told first)
- [ ] Checkpoint (gate): module review
