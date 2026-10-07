# Todo: test-isolation

- [x] Task 1: `state_home()` and derived defaults (D21) — `native_collaboration_runtime.state_home()` reads `AGENT_RELAY_HOME` (empty = unset, relative → `StateHomeError`); `default_root()`, `default_state_root()` and `state_migration.default_target()` derive from it. Migration library keeps `<home>/.agent-relay` unless given `target` (so tests with a temp home never reach the real root); its CLI uses the state root when `--home` is not given and exits 2 on a relative value. New `test_state_home.py` (6 tests); mutation (helper ignores the variable) → red. 280 tests
- [x] Task 2: Entry-point sweep and host entries — runtime, adapters, retire, controller, `cleanup.sh` resolve the root after parsing and exit 2 naming `AGENT_RELAY_HOME` on a relative value; `relay_status.py` answers not ready with that diagnostic; `preflight.sh` prints `runtime root error: …`. `test_state_home.py` sweep (subprocess, empty `HOME`, planted root): runtime `status` ready, `relay_status` ready, retire past the readiness check, controller `list` shows a planted delegation, migration `detect` target ready, preflight prints the relocated root, cleanup reads the relocated mailbox, `HOME` stays empty; `install-codex` / `claude` write the resolved absolute `BRIDGE_DB_PATH` / `XDG_DATA_HOME`; relative value refused by all without a traceback; source scan finds no other `.agent-relay` literal. Mutations (controller, relay_status, retire hardcoding the home) each fail 3 tests. Cleanup test stub gained `StateHomeError`. 284 tests
- [x] Checkpoint (report): every entry point follows `AGENT_RELAY_HOME`
- [ ] Task 3: Seal the test run (D22)
- [ ] Task 4: Docs
- [ ] Task 5: Live moved-root check (round 1 owner told first)
- [ ] Checkpoint (gate): module review
