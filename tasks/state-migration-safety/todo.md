# Todo: state-migration-safety

- [x] Task 1: lock and agent-relay's own bridges (D116, D117) — new `test_state_migration_safety.py` (reuses the `test_state_migration` fixture): a `migrate` while the test holds the lock → blocked "another state migration is running", target tree digest unchanged, no backup; the lock is free again after a migration; an injected agent-relay bridge count → `detect` `target_servers` 2 and a blocker, `migrate` blocked, nothing written. Red 3/3 (no `target_count`), green after `_exclusive` (flock), `migrate` → `_migrate` under the lock, `inspect` `target_count` (default `native_collaboration_runtime._servers_running`) and `Report.target_servers`. On the way: the first lock was a `state-migration.lock` file, which broke 6 existing blocker tests (a blocked migration must write nothing); the lock now is a flock on the state root directory itself (exclusive on macOS, checked with two descriptors), no file; spec assumption 1 and D116 corrected. Without a state root `migrate` only inspects (the runtime cannot be ready). `test_state_migration` 13/13 unchanged
- [ ] Task 2: staged, journalled, all-or-nothing migration (D118, D119)
- [ ] Checkpoint (report): validate on one Python
- [ ] Task 3: interrupted and recover (D120)
- [ ] Task 4: docs (D121)
- [ ] Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`
- [ ] Task 5: live check
- [ ] Checkpoint (gate): module review
