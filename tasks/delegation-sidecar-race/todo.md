# Todo: delegation-sidecar-race

- [x] Task 1: A vanished sidecar is absent, not an error (D71) — `_check_sidecars` calls `lstat()` directly and `continue`s on `FileNotFoundError` (no `exists()` pre-check). New `PrivateStoreTests.test_sidecar_removed_by_concurrent_commit_is_not_an_error`: a real 0600 `-journal` is unlinked just before `lstat()` reads it, `count_delegations` returns 0 — red against main 55c6bad's `session_delegation.py` with `FileNotFoundError: … delegation.sqlite-journal`, green with the fix; `test_unsafe_sidecar_is_rejected_before_database_open` still passes; `test_session_delegation.py` 22 ok (Python 3.10.7). Fix and test were written before the spec while finding the cause; red re-proved after the plan was accepted. CHANGELOG `[Unreleased]` entry
- [ ] Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + 300 runs of the concurrent test on 3.14
- [ ] Checkpoint (gate): module review
