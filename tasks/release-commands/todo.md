# Todo: release-commands

- [x] Task 1: skeleton, output contract and test fixture (D278; AC9)
  - Accepted by the owner: focused suite 14 tests, local path check and `bash scripts/validate.sh` pass (50 files, 989 tests).
- [x] Task 2: `check --pr` (D279; AC1)
  - Accepted by the owner: focused suite 33 tests, local path check and `bash scripts/validate.sh` pass (50 files, 1008 tests).
- [x] Task 3: `prepare` (D280; AC2)
  - Accepted by the owner: focused suite 38 tests, local path check and `bash scripts/validate.sh` pass (50 files, 1013 tests).
- [x] Task 4: `publish` (D281; AC3)
  - Accepted by the owner: focused suite 45 tests, local path check and `bash scripts/validate.sh` pass (50 files, 1020 tests).
- [x] Task 5: `install` host detection and Codex config edit (D282; AC4)
  - Accepted by the owner: focused suite 53 tests, local path check and `bash scripts/validate.sh` pass (50 files, 1028 tests).
- [x] Task 6: `install --confirm` run and verify (D282; AC3, AC5)
  - Accepted by the owner: focused suite 62 tests, local path check and `bash scripts/validate.sh` pass (50 files, 1037 tests).
- [x] Task 7: `upgrade` (D283; AC6)
  - Accepted by the owner: focused suite 69 tests, local path check and `bash scripts/validate.sh` pass (50 files, 1044 tests).
- [x] Task 8: `smoke` and `evidence` (D284, D285; AC7, AC8)
  - Accepted by the owner: focused suite 80 tests, local path check and `bash scripts/validate.sh` pass (50 files, 1055 tests).
- [x] Task 9: `RELEASING.md` calls the subcommands (Requirement 3)
  - Accepted by the owner: also help output is argparse only and the placeholder branch is gone; focused suite 81 tests, local path check and `bash scripts/validate.sh` pass (50 files, 1056 tests).
- [x] Checkpoint (report): owner's read-only dry run of `check` on this Mac
  - Against the real remote, `check --pr 182` (v0.9.6) is `refused` with `main-moved`: D279 requires `<remote>/main` to
    equal the merge commit, so on any release older than main it stops there, and the Plan's `tag-exists` expectation
    cannot be reached that way.
  - Re-run against a local bare copy whose `main` is reset to the v0.9.6 merge commit `48f9a26`, with the real
    `--github` repo for PR and CI lookups: `refused` with `tag-exists` and `version` 0.9.6, so every earlier D279 check
    passed on a real release; no record written.
- [ ] Checkpoint (gate): PR review and merge by the user
