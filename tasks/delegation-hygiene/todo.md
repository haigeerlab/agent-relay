# Todo: delegation-hygiene

- [x] Task 1: review scope in the envelope (D166) — test first in `test_session_delegation_recovery.py`: a scope with bounded-development → `scope-review-only`, `../outside.md` → `scope-outside-project`, a missing path → `scope-missing`, and none of them stores anything; a valid scope (`README.md`, `./docs/`) reaches the host prompt as an `<agent-relay-review-scope>` block naming `README.md, docs` and asking for "Files read:". Red (no `scope` argument), green after `review_scope` (resolved, project-relative, deduplicated, checked before authorizing), `_with_scope`, the `authorize_and_create(scope=…)` parameter and `create --scope` (repeatable)
- [ ] Task 2: the Claude hard limit (D167)
- [ ] Task 3: friendly name as alias (D168)
- [ ] Task 4: prune stuck records (D169)
- [ ] Task 5: interface 2.0 and docs (D170)
- [ ] Checkpoint (report): local validation
- [ ] Task 6: PR and CI
- [ ] Checkpoint (gate): module review
