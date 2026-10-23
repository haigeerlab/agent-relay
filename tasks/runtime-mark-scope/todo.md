# Todo: runtime-mark-scope

- [x] Task 1: the runtime mark (D248) — 5 tests first (red: import error), then `RUNTIME_FILES` / `NOT_RUNTIME_FILES`, `_listed`, `_runtime_mark`, `runtime_mark` and `UPSTREAM_RUNTIME_MARK` (`d426cd2b…`, the mark of the 483756c list kept as `hooks/testdata/upstream-8f12c88.sha256`, whose hash is `UPSTREAM_TREE`); `test_bridge_vendoring` 9 ok; the plugin's mark is `54540368`, as computed for 0.9.0 and 0.9.1
- [x] Task 2: status judges by the runtime mark (D248, D249) — 7 tests first (3 red: test-only and doc-only differences, legacy constant; the fallback cases already held), then `_vendored_current` (the runtime's own `UPSTREAM.sha256`, trusted only when it is a regular file hashing to the manifest `tree`; otherwise the whole-list rule) and the legacy branch on `UPSTREAM_RUNTIME_MARK`; the two older legacy assertions moved to the runtime mark; runtime, vendoring, upgrade, doctor, recovery, rollback, swap-guard and uninstall tests all ok
- [ ] Task 3: upgrade and doctor (AJM8B1H item 5) — upgrade leaves a test-only difference alone; doctor `ok` / reworded `warn` (red), then the doctor detail
- [ ] Task 4: docs (D250) — RELEASING.md two places, CHANGELOG `[Unreleased]`, README / collaboration-ops only if the wording is now wrong
- [ ] Checkpoint (report): local validation — `scripts/validate.sh` on Python 3.9, 3.10, 3.14; read-only `status` and doctor `runtime` on this Mac
- [ ] Task 5: PR and CI — push, PR, four CI jobs green, tell the owner session, ledger comments on PA0EGGT and AJM8B1H
- [ ] Checkpoint (gate): module review
