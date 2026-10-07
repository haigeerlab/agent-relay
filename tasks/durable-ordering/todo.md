# Todo: durable-ordering

- [x] Task 1: Atomic claim and crash injection (assumption 4, D32) — `atomically(db, step)` in delivery.ts (joins an open transaction, else `BEGIN IMMEDIATE`/COMMIT/ROLLBACK) wraps `claim`, `finish`, `recordRead`, `acknowledge` and `expireDue` — not only the claim: an expiry split between the message and its job would have left a pending ping for an expired message. `test/durability.test.ts` 5 tests, failures injected by SQLite triggers that abort the second write, checked from a second connection: send rolls back message and job; claim takes nothing and a later claim succeeds once; finish records neither and the lapse then reads `unknown` on both; expiry expires nothing, then completes and no ping is sent; a bridge dying after submit leaves `unknown`, attempts 1, never re-claimed. 3 red before (send and die-after-submit already held). Mutation (`atomically` without a transaction) → red. 93 TS tests
- [ ] Task 2: Per-recipient order and redundant pings (assumptions 1, 2)
- [ ] Checkpoint (report): ordering and durability green
- [ ] Task 3: Pending cap (D30, D31)
- [ ] Task 4: Docs
- [ ] Task 5: Live D15 (temporary `AGENT_RELAY_HOME`, coordinator told first)
- [ ] Checkpoint (gate): module review
