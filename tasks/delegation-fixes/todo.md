# Todo: delegation-fixes

Round 1 passed on 2026-10-07; code may start.

- [x] Task 1: Held create leaves no blocking record (D15) — D15 revised (keeps the designed same-key retry of a held claim): `_resolve` drops never-launched matches when a launched one shares the name; lone never-launched rows still resolve; `--disambiguator` unchanged. Prove-It test red (`session-name-ambiguous`) then green; mutation (filter off) red; C6 and same-key retry tests green. Test first flaked on `list_delegations` order (same-second `created_at`), fixed by selecting the bound row; 12 consecutive runs green. 240 tests
- [ ] Task 2: Cancel of a never-launched row (D16)
- [ ] Checkpoint (report): finding 3 fixed in unit tests
- [ ] Task 3: Late Claude entry is bound on the next call (D18, round 1 finding 7)
- [ ] Checkpoint (report): finding 7 fixed in unit tests
- [ ] Task 4: Capture the Claude host entry (live, read-only)
- [ ] Task 5: One Claude idle predicate (D17)
- [ ] Checkpoint (report): finding 4 fixed in unit tests
- [ ] Task 6: Docs
- [ ] Task 7: Live C3 and C7
- [ ] Checkpoint (gate): module review
