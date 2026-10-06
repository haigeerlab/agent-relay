# Todo: acceptance-kit

- [x] Task 1: test entry `scripts/validate.sh` and standalone tests (D8) — glob runner: 16 files, 210 tests, all pass (= extracted suite 202 − 1 removed D8 test + 9 in `test_host_config_removal.py`, the C1 copy's own test, which the old suite never ran); breaking one assertion → exit 1; ShellCheck/bash32 clean. Besides D8, the self-wiring assertions in `test_collab_entry.py` and `test_session_routing_entry.py` also read the removed runner; re-pointed to the validate.sh glob (meaning kept, not weakened)
- [ ] Task 2: checklist and record template, with the coverage table
- [ ] Checkpoint (report): tests stand alone, checklist covers the baseline
- [ ] Task 3: preflight and cleanup helpers with tests
- [ ] Checkpoint (gate): module review; the repository is never pushed
