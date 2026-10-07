# Todo: delivery-state-machine

- [x] Task 1: TS suite in the loop — `npm ci --ignore-scripts` in `plugins/agent-relay/bridge` (100 packages; `node_modules`/`dist` git-ignored and skipped by the copy check). `validate.sh` runs `npm run --silent check` (typecheck, build, node tests) inside its seal when `node_modules` exists, adds the TS test count and prints a `bridge: npm run check` line; otherwise prints `skip`. 361 tests (291 Python + 70 TS). A temporary failing TS test made it report FAIL (and the vendored-tree check flagged the unrecorded file); removed. One unsealed in-place `npm run check` before wiring: no writes found in `~/.codex/ipc` or `~/.local/share`
- [ ] Task 2: Schema v3 and Python readers
- [ ] Task 3: Transition core (D28)
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
