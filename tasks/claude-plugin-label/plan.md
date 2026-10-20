# Plan: claude-plugin-label

<!-- spec-guard: review pending -->

Based on [`spec/claude-plugin-label.md`](../../spec/claude-plugin-label.md) (approved by the user on 2026-10-20:
assumptions 1–8, D246–D247; assumption 3 `warn`, assumption 7 README and skills). Built on branch
`claude/charming-hofstadter-ac48c8`. The main clone stays frozen at v0.9.0: no fast-forward, no switch, no
`codex plugin add`; nothing here changes Claude's plugin records before Task 3.

Found while planning (read-only, 2026-10-20): today's check on this Mac is `ok`, with the three stale cache copies
(0.6.1, 0.1.0, 0.5.2) in one long note; `test_doctor.py` already builds fixture copies (`plugin.json` per version) and
calls `_claude_plugin(lambda: listing, version)`, so the new cases reuse that helper.

## Task List

### Task 1: doctor reports a stale label (D246, assumptions 2, 3, 6; D247 advice per assumption 4)
Red first, in `test_doctor.py` on fixture listings: label = loaded version → `ok`; the measured shape (live local
records labelled 0.6.1 / 0.5.2 / 0.1.0, `readFromFolder` = a 0.9.0 copy, a user record labelled 0.9.0) → `warn`,
the detail naming each distinct label once with the loaded version and path, `next` giving per live folder
`cd <folder> && claude plugin uninstall --scope local agent-relay@agent-relay-marketplace`; the same without a user
record → `claude plugin update --scope local …` in that folder instead; a user record whose label lags → marketplace
update then `claude plugin update --scope user …`; only gone-folder records mismatched → `ok` with a count; missing or
non-string label → no mismatch; the old "not loaded while readFromFolder is set" note no longer appears (merged); every
existing D184 case still passes. Green: `_claude_plugin` in `native_collaboration_doctor.py`, still read-only.

### Task 2: README, skills and CHANGELOG (assumption 7, 8)
Red first, guard tests in `test_skill_entrypoints.py`: README.md and README.en.md "更新插件" / plugin-update section say
a `claude plugin list` version that disagrees with doctor is a stale label and doctor says how to clear it; `collab`
and `collaboration-ops` tell agents to answer "which version is loaded" from doctor's `claude-plugin`, never from the
listing's `version`. Green: the text, plus a CHANGELOG `[Unreleased]` entry.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 (Node 24 first on PATH); doctor's `claude-plugin` run read-only
from this worktree on this Mac (expected `warn` naming 0.6.1 / 0.5.2 / 0.1.0) recorded in the todo.

### Task 3 (gate): host measurements — only after the user ends the 0.9.0 freeze **and** separately consents
Each command changes the user's Claude plugin records; ask once per step, naming the folder/record it touches.
(a) In one live folder with a stale local record and an enabled user record: `claude plugin uninstall --scope local
agent-relay@agent-relay-marketplace`, then a new session there — does it still load the clone via the user record?
(b) Does `claude plugin update --scope local` / `--scope user` refresh the label when the marketplace is the local
clone? (c) Can a record whose folder is gone be removed with the CLI at all? Record results in the todo. If any result
differs from assumption 4, the advice is corrected test-first (Task 1's cases) and the spec gets a change-log line.
Cleanup of the remaining records stays the user's, step by step.

### Task 4: PR and CI
Only after Task 3, so no unmeasured advice is merged. Push, open the PR (Chinese title and body), tell the
agent-relay owner session the number; the four CI jobs green.

### Checkpoint (gate): module review
Round-2 coordinator review; the user merges. The 0.9.1 release is a separate step, asked of the user after the freeze.
