# Todo: idempotency

- [x] Task 1: Key check (D33, D34, assumptions 1, 2, 5) — `src/idempotency.ts` (`contentDifferences` on toAgent/body/threadId, `conflictError`, `duplicateWarning`); `BridgeStore.deliver()` returns `{ message, duplicate }`, `send()` unchanged for internal callers; refusal skipped for `bridge` (notices fold by key); duplicate return stays before the cap check. `bridge_send` returns `duplicate: true` + "already stored as message #N; not sent again". `test/idempotency.test.ts` 6 tests (red before: module missing): identical retry one wake job; toAgent/body/threadId (incl. thread → null) each refused with key, id, state and "no resend is needed", one row; wake/timeout ignored; bridge notices fold; at the cap retry passes and conflict refused as conflict; MCP-level duplicate flag and refusal text. Upstream `bridge-store.test.ts:60` unchanged and green. Mutation (refusal disabled) → red. 110 TS tests, validate 409
- [ ] Task 2: Schema v4 and Python readers (assumption 3)
- [ ] Task 2b: Delegation result route (coordinator, 2026-10-07)
- [ ] Checkpoint (report): key check and schema green
- [ ] Task 3: Reply link (assumption 3, D36)
- [ ] Task 4: Reply de-duplication (D35)
- [ ] Task 5: Docs
- [ ] Task 6: Live D14 (temporary `AGENT_RELAY_HOME`, coordinator told first)
- [ ] Checkpoint (gate): module review
