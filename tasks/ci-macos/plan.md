# Plan: ci-macos

Based on [`spec/ci-macos.md`](../../spec/ci-macos.md) (accepted by the user on 2026-10-08: assumptions 1–8, D80–D82,
D80a full 2 × 2). Branch `claude/ci-macos` from main d7a7778. Red → green, one commit per task.

## Task List

### Task 1: doctor names its toolchain (D81)
Python test first (`hooks/test_doctor.py`): `toolchain` check present with and without a runtime, naming
`sys.executable`, the Python version and the selected node's path, version and source; `warn` with the install hint
when node selection fails. Then `native_collaboration_doctor.py`. collaboration-ops skill mentions it. CHANGELOG.
**Files:** `hooks/native_collaboration_doctor.py`, `hooks/test_doctor.py`, `skills/collaboration-ops/SKILL.md`,
`CHANGELOG.md`.

### Task 2: the workflow (D80, D80a, D82)
Static test first (`hooks/test_ci_workflow.py`, plain text checks, no YAML library): the file exists; triggers are
`pull_request`, `push` to `main`, `workflow_dispatch`; no `pull_request_target`; `permissions: contents: read`; every
`uses:` is pinned to a 40-hex SHA; checkout has `persist-credentials: false`; runner `macos-15`; matrix Python 3.9 /
3.14 × Node 22 / 24; the 3.9 leg uses `/usr/bin/python3` and asserts 3.9.x; the doctor `toolchain` line is printed;
`validate.sh` runs and the job fails if the bridge check was skipped. Then `.github/workflows/ci.yml`. README "CI" note
(what runs; how the user can make it required, D82). CHANGELOG.
**Files:** `.github/workflows/ci.yml`, `plugins/agent-relay/hooks/test_ci_workflow.py`, `README.md`, `CHANGELOG.md`.

### Checkpoint (report): local validation on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 3: first CI run on GitHub
Approving this plan approves pushing `claude/ci-macos` and opening a **draft** PR so the workflow runs (CI cannot run
otherwise). Read the four jobs' results; if a test depends on this Mac, fix the isolation (one commit per fix, red
shown by the CI log, green by the next run); a product change found this way stops for the user. Record each job's
Python, Node and "bridge: npm run check ok" lines in the todo.

### Checkpoint (gate): module review
With CI green on the draft PR. After approval the PR is marked ready for review; required-check settings stay the
user's (D82).
