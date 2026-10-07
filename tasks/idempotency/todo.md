# Todo: idempotency

- [x] Task 1: Key check (D33, D34, assumptions 1, 2, 5) — `src/idempotency.ts` (`contentDifferences` on toAgent/body/threadId, `conflictError`, `duplicateWarning`); `BridgeStore.deliver()` returns `{ message, duplicate }`, `send()` unchanged for internal callers; refusal skipped for `bridge` (notices fold by key); duplicate return stays before the cap check. `bridge_send` returns `duplicate: true` + "already stored as message #N; not sent again". `test/idempotency.test.ts` 6 tests (red before: module missing): identical retry one wake job; toAgent/body/threadId (incl. thread → null) each refused with key, id, state and "no resend is needed", one row; wake/timeout ignored; bridge notices fold; at the cap retry passes and conflict refused as conflict; MCP-level duplicate flag and refusal text. Upstream `bridge-store.test.ts:60` unchanged and green. Mutation (refusal disabled) → red. 110 TS tests, validate 409
- [x] Task 2: Schema v4 and Python readers (assumption 3) — v4 migration: nullable `messages.reply_to` + partial index `idx_messages_reply`; `BridgeMessage.replyTo`. `test/schema.test.ts`: v2 mailbox (fresh store with v3/v4 columns dropped, `user_version = 2`) → one open → `{from: 2, to: 4}`, exactly one backup `bridge-pre-v4-from-v2-*` holding the v2 file (2 messages, 1 ack), inbox and key retry work after; older-process insert into v4 reads `replyTo: null` (both red before). v3 test now asserts `to: SCHEMA_VERSION`. Python `MAILBOX_SCHEMA_VERSIONS = (2, 3, 4)`; retire and delegation-backend tests read v3 and v4, refuse v5 (red before). `upgrade --confirm` on a v2 runtime with counts intact is the existing `test_runtime_upgrade` case (the upgrade does not open the mailbox; the bridge migrates on first open) — the joined path on a real build is added to Task 6. `relay_status.py` untouched
- [ ] Task 2b: Delegation result route (coordinator, 2026-10-07)
- [ ] Checkpoint (report): key check and schema green
- [ ] Task 3: Reply link (assumption 3, D36)
- [ ] Task 4: Reply de-duplication (D35)
- [ ] Task 5: Docs
- [ ] Task 6: Live D14 (temporary `AGENT_RELAY_HOME`, coordinator told first)
- [ ] Checkpoint (gate): module review
