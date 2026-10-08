# Todo: delegation-claim

- [x] Task 1: the claim file (D122) — new `test_delegation_claim.py` `ClaimFileTests` (6): `claims/` 0700 and the file 0600, clean at first; a second holder in the same process and a lock held through another descriptor → `OperationBusy`, free again after release; `begin("create")` survives reopening (`previous()` reads it), `end()` empties it; a symlinked lock file and a directory in its place → `DelegationError("claim-file-unsafe")`; a non-canonical delegation id (`../escape`) refused. Red at import, green after `OperationClaim` / `OperationBusy` in `session_delegation.py` (canonical UUID check, private directory check, `O_NOFOLLOW` open, regular-file/owner/0600 check on the descriptor, `flock(LOCK_EX|LOCK_NB)`, `begin`/`end` truncate + write + fsync)
- [ ] Task 2: the controller takes the claim; busy and interrupted results (D123, D124, D125)
- [ ] Checkpoint (report): validate on one Python
- [ ] Task 3: docs (D126)
- [ ] Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`
- [ ] Task 4: live check
- [ ] Checkpoint (gate): module review
