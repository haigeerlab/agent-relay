# Todo: bridge-vendoring

- [x] Task 1: Vendor the bridge and record provenance (D23, D25a) — 54 of upstream's 62 files written from the `8f12c88` git blobs of the local runtime checkout (read-only) into `plugins/agent-relay/bridge/` (528 KB); left out exactly `skills/`, `agents/`, `assets/`, `.github/`, `scripts/generate-demo-gif.py`. **D25a pass:** `git hash-object` of every vendored file equals its blob at `8f12c88` (0 mismatches); all upstream modes are 100644. `UPSTREAM.md` (repository, commit, MIT notice, left-out list, "agent-relay changes: none") and `UPSTREAM.sha256` (54 lines, `shasum -c` all OK). `verify_bridge_copy()` refuses a changed, missing or extra file or a symlink; `test_bridge_vendoring.py` (4 tests): tree matches, provenance and licence kept, left-out paths absent, edit/add/remove refused. Mutation (check disabled) → refusal test red. 289 tests
- [ ] Task 2: Install from the vendored copy (D24)
- [ ] Checkpoint (report): installer uses the verified copy
- [ ] Task 3: Docs
- [ ] Task 4: Live identity proof (D25b–d; round 1 owner told first)
- [ ] Checkpoint (gate): module review
