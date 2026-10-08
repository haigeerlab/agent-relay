# Spec: ack-wake-atomic

## Objective

The 0.4.0 architecture review found that acknowledging a message and closing its wake job happen in two transactions.
`BridgeStore.ack` inserts the acknowledgement in autocommit mode and then calls `wakes.acknowledge`, which opens its
own transaction; with several ids, each id commits on its own. A failure or a kill between the two leaves a message
acknowledged while its wake job is still `pending` (or `sending`, `accepted`, `read`, `held`, `unknown`); the
dispatcher may then claim that job and ping the recipient about work it already finished. The user chose
(2026-10-09) to fix this as the last remaining review finding.

Readers: the user; the round-2 coordinator, who reviews the PR before the user merges.

## What exists today (main 9eb58f2, 2026-10-09)

- `bridge/src/bridge-store.ts:477-495` `ack(agent, messageIds, note)`: a prepared `INSERT OR IGNORE INTO
  acknowledgements … WHERE m.id = ? AND DELIVERED_TO(?)` run per id in autocommit; when it inserted a row,
  `this.wakes.acknowledge(agent, id)`; returns the number newly acknowledged.
- `bridge/src/wake-queue.ts:136-152` `acknowledge` → `atomically(db, acknowledgeStep)`: closes the message's open wake
  jobs as `acknowledged` and follows the message's delivery state.
- `bridge/src/delivery.ts:33-44` `atomically`: `BEGIN IMMEDIATE` … `COMMIT`, `ROLLBACK` on error; inside an open
  transaction it just runs the step.
- Callers: `bridge/src/server.ts:426` (`bridge_wait` with `acknowledge`), `:454` (`bridge_ack`).

## Assumptions (accepted by the user 2026-10-09)

1. Only `BridgeStore.ack` changes: the whole loop (insert and wake closure for every id) runs inside one
   `atomically`; `wakes.acknowledge` nested in it runs without a transaction of its own. Callers unchanged.
2. Any failure rolls the whole call back: no acknowledgement recorded, wake jobs unchanged; the error reaches the
   tool caller as today. The return value, `INSERT OR IGNORE` idempotency and the delivered-only guard are unchanged.
3. Other two-step writes (read receipts, activity refresh) are out of scope.
4. `interface.json` stays 1.4; no new fields.
5. Red first: two ids acknowledged in one call with a failure injected while closing the second wake job → neither
   message has an acknowledgement and both wake jobs keep their state (today the first message stays acknowledged with
   its job closed while the second is acknowledged with its job open, or similar partial states); the normal path and
   existing tests unchanged. Regenerate `UPSTREAM.sha256`; `UPSTREAM.md` row; CHANGELOG.
6. A bridge change: the real host gets it with the next release and runtime upgrade; no release in this module.
7. Validate on Python 3.9, 3.10, 3.14 (bridge check included); no live check (the fault needs injection; the unit
   test runs on real SQLite).
8. The round-2 coordinator reviews the PR; the user merges after every CI check has finished green.

## Decisions

- **D130 one transaction.** `ack` becomes `return atomically(this.db, () => { … the existing loop … })`. No other change
  to its body.
- **D131 docs.** `UPSTREAM.md` row for `src/bridge-store.ts` and the new test, manifest regenerated, CHANGELOG
  `[Unreleased]`.

## Requirements

0. Red first (new `bridge/test/ack-atomic.test.ts`, a temporary database): register a sender and a recipient, send two
   messages with `wake: true` and a wake binding so both have open wake jobs; replace `store.wakes.acknowledge` (or the
   prepared step it runs) so the second call throws; `store.ack(recipient, [a, b])` throws; afterwards no
   `acknowledgements` row exists for either message and both wake jobs are still in their open state. Then the same
   call without the fault acknowledges both and closes both jobs, and a repeated `ack` returns 0.
1. Existing bridge tests stay green unchanged.
2. Validate on three Pythons; CI green (all checks finished).

## Boundaries

- Always: temporary databases in tests; regenerate `UPSTREAM.sha256` after any bridge change.
- Never: change what `ack` returns or which messages it accepts; merge before the coordinator's review and finished CI.

## Success criteria

After any `bridge_ack` (or acknowledging `bridge_wait`), either every acknowledged message has its wake job closed, or
nothing changed.

## Open questions

None. Assumptions 1–8 accepted on 2026-10-09 ("成立"); the spec (D130, D131) accepted on 2026-10-09 ("接受").
