# Plan: ack-wake-atomic

Based on [`spec/ack-wake-atomic.md`](../../spec/ack-wake-atomic.md) (accepted by the user on 2026-10-09: assumptions
1–8, D130, D131). Branch `claude/ack-wake-atomic` from main 9eb58f2. Red → green. The round-2 coordinator reviews the
PR; the user merges after every CI check has finished green. No release here.

Code: `bridge/src/bridge-store.ts`; test: new `bridge/test/ack-atomic.test.ts`. Regenerate `UPSTREAM.sha256` after any
bridge change. Record validate only after its output says `validate: pass`.

## Task List

### Task 1: one transaction for ack and its wake closures (D130, D131)
Red first: two messages with open wake jobs; the second wake closure throws → `ack` throws, no acknowledgement for
either, both jobs still open; without the fault both are acknowledged and closed, a repeat returns 0. Then wrap
`ack` in `atomically`. `UPSTREAM.md` row, manifest, CHANGELOG.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Checkpoint (gate): module review
Then push and PR with the user's approval; the round-2 coordinator reviews; the user merges after CI has finished green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A caller already inside a transaction | Low | `atomically` runs the step directly inside an open transaction |
| Longer write lock during a large ack | Low | ids are few per call; same statements as today |
