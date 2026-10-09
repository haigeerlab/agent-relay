# Todo: delegation-continue-parity

- [x] Task 1: store schema 3 (D172) — new `test_delegation_schema3.py` (red: no `scope`, version 2): a 0.6.0-shaped store migrates in place to 3 with records intact, `scope`/`state_reason` NULL, and a 0600 copy `delegation.schema2.sqlite` taken once with SQLite's backup API; a crash inside the migration transaction leaves schema 2 without the columns and the next open migrates; new stores are 3 with no copy; `claim_launch(scope=…)` stores the scope (`()` when none) and a held create's retry takes the retry's scope; `bind_host`/`record_host_unknown`/`begin_follow_up`/`advance`/`prune_stale` write `state_reason`; a non-list scope is invalid contents. Public output adds `stateReason` without the `host-` prefix (existing no-internals tests). Fixtures updated: `test_state_migration` row width, `test_delegation_store_init` uses `SCHEMA_VERSION`. All 524 hook tests OK (Python 3.10.7)
- [ ] Task 2: continue keeps the limits (D171)
- [ ] Task 3: prune confirms by id (D173)
- [ ] Task 4: pre-flight accuracy and dead code (D174)
- [ ] Task 5: scope hook gaps (D174)
- [ ] Checkpoint (report): local validation and real check
- [ ] Task 6: PR and CI
- [ ] Checkpoint (gate): module review
