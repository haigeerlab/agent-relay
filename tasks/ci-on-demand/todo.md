# Todo: ci-on-demand

- [x] Task 1: the scope decision (D135) — new `hooks/test_ci_scope.py` (12 tests: exempt-only skips on `pull_request` and `push`; one non-exempt path is full and named; look-alikes `spec.md`, `specs/x.md`, `tasks.md`, `.agent-relay/x`, `.agent`, `spec`, `docs/CLAUDE.md`, `plugins/agent-relay/AGENTS.md`, `docs/spec/x.md`, `claude.md`, `README.md`, `CHANGELOG.md` are full; empty or unreadable list is full; `schedule`, `workflow_dispatch`, `pull_request_target`, `merge_group` and no event are full; in a real git repository: exempt-only PR skips and writes `scope=skip` to `$GITHUB_OUTPUT`, the PR diff is taken from the merge base (main moving on with code does not count), a code change, a move of code into `spec/` and a deletion are full, an all-zeros, empty or unreachable base is full, `schedule` is full without a diff): 12 red (no script), green after `scripts/ci_scope.py` (stdlib; `git diff --name-only --no-renames`, three-dot for PRs, two-dot for pushes). Green on Python 3.10.7 and Apple 3.9.6. Dropping `--no-renames` turns the move test red (checked, then restored)
- [ ] Task 2: the guard (D137)
- [ ] Task 3: the workflow, README and CHANGELOG (D136, D138, D139)
- [ ] Checkpoint (report): local validation
- [ ] Task 4: the module's PR runs full
- [ ] Task 5: real `skip` evidence
- [ ] Checkpoint (gate): module review
