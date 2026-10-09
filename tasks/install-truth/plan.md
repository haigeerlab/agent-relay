# Plan: install-truth

Based on [`spec/install-truth.md`](../../spec/install-truth.md) (accepted by the user on 2026-10-10: assumptions 1–6,
D184–D185). Branch `claude/install-truth` from main after this plan's PR. Second and last module of 0.6.2. The round-2
coordinator is told every PR number.

Found while planning (read-only `claude plugin list --json`, Claude Code 2.1.295): besides the user-scope entry
(`installPath` = cache `0.5.2`, `readFromFolder` = the clone, `folderVersion` 0.6.1), there are eight **local-scope**
entries (`scope: "local"`, one per `projectPath`, several of them deleted worktrees), all with `installPath` = the cache's
`0.1.0` directory and the same `readFromFolder`. The cache holds only `0.1.0` and `0.5.2`; each `plugin.json` matches
its directory name. So the check groups copies by path (one line per stale copy, naming the scopes and projects that use
it) instead of one warning per entry, and the real check in Task 4 also finds what clears a local-scope entry.

## Task List

### Task 1: doctor `claude-plugin` check (D184, assumption 2)
Red first, on fixture listings passed in (no real `claude`): every enabled agent-relay copy (`installPath`, and
`readFromFolder` when present) whose `.claude-plugin/plugin.json` version equals the running plugin's → `ok`; the measured
shape (user scope: `readFromFolder` 0.6.x, `installPath` 0.5.2; listing `version` 0.1.0) → `warn` naming the
`installPath` copy, its version, its scopes/projects, and the next step (`claude plugin marketplace update
agent-relay-marketplace`, `claude plugin update agent-relay@agent-relay-marketplace`, restart open Claude sessions); a
listing `version` that disagrees with the files is ignored; a copy whose `plugin.json` is missing or unreadable → `warn`
saying so; disabled entries and other plugins ignored; no `claude` binary → `skip`; non-zero exit or malformed JSON →
`skip` with the reason. Green: `_claude_plugin(listing)` in `native_collaboration_doctor.py`, reading files only; the
listing comes from `claude plugin list --json` with a timeout.

### Task 2: skills give exact arguments (D185, assumptions 3–5)
Red first (skill guard tests in `test_skill_entrypoints.py`): session-routing lists, for each selector field, exactly the
values of the matching set in `session_routing.py` (`HOSTS`, `AUTHORIZATION_STATES`, `TARGET_RESOLUTIONS`,
`NATIVE_CAPABILITIES`, `NATIVE_DISPATCHES`, `BRIDGE_STATES`, and the joined booleans); collab has one literal
`bridge_register` call per host (Claude `{agent, wake}`, Codex with `host`/`wake` object); collab says that a name held by
a stopped session gets a new name first, `takeover` only if the user wants that exact name. Green: the skill text.

### Task 3: README and CHANGELOG (assumptions 1, 6) — written after Task 4's measurement
Red first: guard tests that README "升级" and the CHANGELOG name both Claude commands and the restart (desktop Code tab
included). Green: README per install kind, `[0.6.1]` correction note, `[Unreleased]` entry; wording from Task 4's result.

### Task 4: real check on this Mac — **ask the user first** (it changes their Claude plugin install)
Run `claude plugin marketplace update agent-relay-marketplace` and `claude plugin update agent-relay@agent-relay-marketplace`;
record what appears under `~/.claude/plugins/cache/agent-relay-marketplace/agent-relay/`, how the listing's user- and
local-scope entries change, and whether a reopened desktop Code-tab session loads the new skills (e.g. session-delegation
mentions `prune`). If the local-scope entries stay on 0.1.0, find what clears them (e.g. `--scope local` per project) and
document only what was measured. Doctor's new check is run before and after.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 (Node 24 first on PATH); doctor's `claude-plugin` output on this Mac
recorded in the todo.

### Task 5: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.2 release PR.
