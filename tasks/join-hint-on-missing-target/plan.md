# Plan: join-hint-on-missing-target

Based on [`spec/join-hint-on-missing-target.md`](../../spec/join-hint-on-missing-target.md) (accepted by the user on
2026-10-12: assumptions 1–6, D192). Branch `claude/join-hint-impl` from main after this plan's PR. Only module of
0.6.6; the round-2 coordinator is told every PR number. The release PR is opened only after the implementation PR is
merged.

## Task List

### Task 1: the selector's `nextStep`
Red first in `hooks/test_session_routing.py`: the three reasons carry `nextStep` with the exact sentence, at most 240
characters; every other result has no `nextStep`; unknown input fields are still rejected. Green: one constant
(`JOIN_HINT`) and `_decision(..., next_step=...)` in `hooks/session_routing.py`.

### Task 2: the skills say it
Red first in `test_session_routing_entry.py` and `test_collab_entry.py`: both skills contain the sentence, equal to
the selector's constant; the routing skill tells the session to replace `<名字>` with a name it picks and not to put
the user's wording into a command. Green: `skills/session-routing/SKILL.md` (the `stop` bullet and the zero-match
paragraph) and `skills/collab/SKILL.md` (the zero-match line). Check for a Codex copy of either text
(`references/`, `.codex-plugin`) and keep them the same.

### Task 3: CHANGELOG
`[Unreleased]`: the change, "update the plugin and open a new session", no runtime upgrade.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH.

### Task 4: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.6 release PR.
