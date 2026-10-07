# Todo: test-isolation

- [x] Task 1: `state_home()` and derived defaults (D21) — `native_collaboration_runtime.state_home()` reads `AGENT_RELAY_HOME` (empty = unset, relative → `StateHomeError`); `default_root()`, `default_state_root()` and `state_migration.default_target()` derive from it. Migration library keeps `<home>/.agent-relay` unless given `target` (so tests with a temp home never reach the real root); its CLI uses the state root when `--home` is not given and exits 2 on a relative value. New `test_state_home.py` (6 tests); mutation (helper ignores the variable) → red. 280 tests
- [ ] Task 2: Entry-point sweep and host entries
- [ ] Checkpoint (report): every entry point follows `AGENT_RELAY_HOME`
- [ ] Task 3: Seal the test run (D22)
- [ ] Task 4: Docs
- [ ] Task 5: Live moved-root check (round 1 owner told first)
- [ ] Checkpoint (gate): module review
