# Todo: delivery-state-machine

- [x] Task 1: TS suite in the loop — `npm ci --ignore-scripts` in `plugins/agent-relay/bridge` (100 packages; `node_modules`/`dist` git-ignored and skipped by the copy check). `validate.sh` runs `npm run --silent check` (typecheck, build, node tests) inside its seal when `node_modules` exists, adds the TS test count and prints a `bridge: npm run check` line; otherwise prints `skip`. 361 tests (291 Python + 70 TS). A temporary failing TS test made it report FAIL (and the vendored-tree check flagged the unrecorded file); removed. One unsealed in-place `npm run check` before wiring: no writes found in `~/.codex/ipc` or `~/.local/share`
- [x] Task 2: Schema v3 and Python readers — `SCHEMA_VERSION = 3`; `MIGRATIONS[2]` adds nullable `messages.delivery_state`, `delivery_changed_at`, `read_at`, `expires_at` and `idx_messages_delivery`. TS tests (red → green): v2 file migrates to v3 with `{from: 2, to: 3}` and its rows, columns nullable; an older-process INSERT leaves `delivery_state` NULL. Python: `MAILBOX_SCHEMA_VERSIONS = (2, 3)` in `native_collaboration_runtime`, used by retire and both delegation-backend checks; tests: v3 read, v4 refused (red on v3 before). `state_migration` needs no change (message states are not wake states; the new wake state of Task 6 is final). New `scripts/bridge-manifest.py` rewrites `UPSTREAM.sha256`; `UPSTREAM.md` gains a change table. `test_the_unmodified_upstream_tree_is_recorded` replaced by `…moved_past_the_upstream_tree` (a git-installed runtime now reads `current: false`, as intended). 365 tests (293 Python + 72 TS)
- [x] Task 3: Transition core (D28) — new `src/delivery.ts`: `DeliveryState`, the transition table (queued → sending/accepted/expired; sending → queued/accepted/failed/unknown; unknown → accepted; accepted/failed/expired final), `transition()` as a conditional UPDATE (refuses illegal moves and concurrent changes), `deliveryState()` (NULL = queued, broadcast = null), `queueTimeoutMs()` (`BRIDGE_QUEUE_TIMEOUT_MS`, 1 min … 7 d, else 24 h) and `sendTimeoutMs()`. Send writes `queued`, `delivery_changed_at`, `expires_at` for direct messages; `BridgeMessage` gains `deliveryState`, `expiresAt`; `bridge_send` takes `expiresInSeconds` (60 … 604800). `test/delivery-state.test.ts` 5 tests (all 36 from/to pairs checked); red at compile before. Mutation (table check off) → 1 failure. 77 TS tests
- [ ] Task 4: Wake results drive the message state, `unknown` never replayed
- [ ] Checkpoint (report): state machine drives every wake outcome
- [ ] Task 5: Expiry and inbox filters (D27)
- [ ] Task 6: Ack closes the wake job (finding 5)
- [ ] Task 7: Surface the state (D29)
- [ ] Checkpoint (report): bridge side complete
- [ ] Task 8: Upgrade command (bridge-vendoring D26)
- [ ] Task 9: Docs and provenance
- [ ] Task 10: Live checks (coordinator, user go-ahead)
- [ ] Checkpoint (gate): module review
