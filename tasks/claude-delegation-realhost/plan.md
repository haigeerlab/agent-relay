# Plan: claude-delegation-realhost

Based on [`spec/claude-delegation-realhost.md`](../../spec/claude-delegation-realhost.md) (accepted by the user on
2026-10-10: assumptions 1–5, D181–D183). Branch `claude/claude-delegation-realhost` from main after #71. First module
of 0.6.2. The round-2 coordinator is told every PR number.

Found while planning (read-only query of the real delegation store, schema 3 records the reason): the failed
`cx2cc-readme` record has `last_turn_ref = claude-reregister-<session>` and `state_reason = host-result-unknown`. So the
first turn ended `created` without registration as designed, a `continue` then took the D49 re-send path, and it was
`_deliver` (wake or stop-and-resume of that re-send) that moved the record to `unknown`. `cx2cc-readme2` completed
normally. Task 1 finds which `_deliver` branch did it; the likely one is H1's (`done` read as not stopped), which the
wake/resume decision also uses.

## Task List

### Task 1: trace the H2 record to its `_deliver` branch
Read only: the coordinator's session 6472d974 transcript and `claude agents --json --all` shape for it (if still
listed), against each `advance(..., "unknown", ...)` in `_deliver`. Record the branch and the host facts in the todo; if
it is not H1's, the fix for it joins Task 3.

### Task 2: `done` is a stopped Claude session (D181)
Red first: an adapter test whose agents entry is verbatim Claude Code 2.1.295 after `claude stop` (`"state": "done"`,
no `status`, no `pid`) resumes with one `--resume` carrying the launch limits (today: `held/target-status-unknown`);
the same entry on the re-send path resumes too. Green: `_deliver` treats `done` like `stopped`/`exited`/`failed`.

### Task 3: the delegated session can load its mailbox tools (D182)
Red first: every launch shape's `--tools` contains `ToolSearch` and the resume argv still equals the create argv minus
`--name` plus `--resume`; an `unknown` record's continue error names `cancel` then create as the next step; whatever
Task 1 found that is not H1 is covered here. Green: `ToolSearch` in `_permission_shape`'s tool lists; the error text.

### Task 4: truthful prune help (D183)
`prune --help` says `--confirm ID,...` cancels the listed ids (guarded by a help-text test).

### Checkpoint (report): local validation and real checks
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14. Real checks on this Mac (spec assumption 5): (a) through the
adapter, create a `README.md`-scoped review, let it complete, `claude stop` it, continue: it resumes and a read outside
the scope is denied; (b) **with the user's consent** stop every bridge, then three creates in a row: all register and
report back, or the fallback keeps them `created` + `mailbox-registration-missing` and the re-send completes them; none
goes `unknown`. CHANGELOG `[Unreleased]`.

### Task 5: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then `install-truth`.
