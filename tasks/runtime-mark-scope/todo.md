# Todo: runtime-mark-scope

- [ ] Task 1: the runtime mark (D248) — classification test, mark tests, legacy constant test (red), then `RUNTIME_FILES` / `NOT_RUNTIME_FILES`, `runtime_mark`, the legacy constant
- [ ] Task 2: status judges by the runtime mark (D248, D249) — test-only difference current, `src/` difference not, missing or mismatched runtime list falls back, legacy constant (red), then `_status`
- [ ] Task 3: upgrade and doctor (AJM8B1H item 5) — upgrade leaves a test-only difference alone; doctor `ok` / reworded `warn` (red), then the doctor detail
- [ ] Task 4: docs (D250) — RELEASING.md two places, CHANGELOG `[Unreleased]`, README / collaboration-ops only if the wording is now wrong
- [ ] Checkpoint (report): local validation — `scripts/validate.sh` on Python 3.9, 3.10, 3.14; read-only `status` and doctor `runtime` on this Mac
- [ ] Task 5: PR and CI — push, PR, four CI jobs green, tell the owner session, ledger comments on PA0EGGT and AJM8B1H
- [ ] Checkpoint (gate): module review
