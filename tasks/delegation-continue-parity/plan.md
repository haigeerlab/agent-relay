# Plan: delegation-continue-parity

Based on [`spec/delegation-continue-parity.md`](../../spec/delegation-continue-parity.md) (accepted by the user on
2026-10-09: assumptions 1–9, D171–D174). Branch `claude/delegation-continue-parity` from main after #63. First module
of 0.6.1. The round-2 coordinator is told every PR number; no release before it has reviewed all three module PRs and
the user agrees.

Checked while planning (assumption 9): Codex continue already re-sends the thread's `approvalPolicy` and `sandbox`
(`session_delegation_codex.py:772-773`), so Codex has no launch-shape gap; only its soft scope text is missing on a
continue (Task 2 re-adds the scope block for both hosts). The Claude MCP config is cached per process
(`ClaudeAdapter._configs`); a continue runs in a new process, so it regenerates the config with `config_factory`.

## Task List

### Task 1: store schema 3 (D172)
Red first (`test_session_delegation*.py`): a schema-2 store built the 0.6.0 way opens as 3 with every record intact and
`scope`/`state_reason` NULL; reopening is a no-op; a migration stopped before `user_version = 3` re-runs cleanly; a copy
of the schema-2 file is left next to the store before the first change; create stores the normalized scope (`[]` when
none); every `advance` and `prune_stale` writes its evidence to `state_reason`; `status` shows it.

### Task 2: continue keeps the limits (D171)
Red first (`test_session_delegation_claude.py`, recovery): one function builds the limit flags for create and continue;
for both intents, with and without user environment and scope, the continue argv equals the create argv minus
`--name <n>` plus `--resume <session>`; the resume used by `_resend_registration` gets the same flags; a continue
re-adds the `<agent-relay-review-scope>` block for both hosts; a pre-schema-3 Claude `safe-review` record is refused
`scope-unknown` without touching the host; a `bounded-development` one continues without scope.

### Task 3: prune confirms by id (D173)
Red first (recovery): `prune --confirm <id,…>` cancels only listed ids still stale and not live; a record that turned
stale after the preview is left; unknown, ambiguous and no-longer-stale ids are reported as skipped; `--confirm`
without ids fails; a second run finds none.

### Task 4: pre-flight accuracy and dead code (D174)
Red first: `_matches_rule` accepts `mcp__<server>` and `mcp__<server>__*` for that server's tools only; the `plan` and
`dontAsk` branches of `_permission_shape` are gone and an unknown intent still raises.

### Task 5: scope hook gaps (D174)
Red first (`test_delegation_scope_hook.py`): Glob `{path: "docs", pattern: "../other.txt"}` and an absolute pattern
outside the scope are denied; inside ones still allowed. Real check first: whether `--settings
'{"disableAllHooks": false, …}'` keeps the hook running in a project whose `.claude/settings.json` sets
`disableAllHooks: true`; then either add the key or refuse a scoped review in such a project (`scope-hook-disabled`).

### Checkpoint (report): local validation and real check
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14; on this Mac a scoped Claude review continued once still
answers DENIED outside its scope. CHANGELOG `[Unreleased]` entry.

### Task 6: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews the PR; the user merges; then `presence-polish`.
