# Spec: delegation-continue-parity

## Objective

First module of 0.6.1. The round-2 coordinator's post-release review of 0.6.0 (#54–#62, 2026-10-09), accepted by the
user ("按你的推荐，两点都同意"), found that a continued Claude Code delegation loses every limit it was created with,
and that `prune --confirm` can cancel records the user never saw. This module fixes both and the small delegation
findings that sit in the same files.

Readers: the user; the round-2 coordinator (acceptance after 0.6.1).

## What exists today (main 835304b, v0.6.0)

- **Continue drops the launch shape** (review item 1). `ClaudeAdapter` continues with only
  `claude --background --resume <session> <prompt>` (`session_delegation_claude.py:816`). The create command carries
  `--mcp-config`, `--strict-mcp-config`, `--setting-sources`, `--permission-mode`, `--permission-prompts none`,
  `--disable-slash-commands`, `--no-chrome`, `--tools` and, for a scoped review, the scope hook in `--settings`
  (`build_create_command`, lines 308–343).
  - Measured 2026-10-09 (Claude Code 2.1.295, `claude -p --model haiku`, project with `README.md` and `other.txt`):
    created with `--session-id X --permission-mode dontAsk --tools Read --setting-sources project,local
    --strict-mcp-config --settings <scope hook for README.md>` → `other.txt` **DENIED**; then
    `claude -p --resume X` without flags → `other.txt` **read**, and the turn had Bash, Edit, Write, Skill, Agent and
    the user's MCP servers. Flags are per process; `--resume` keeps the conversation, not the limits.
- **The scope is not stored** (delegation-hygiene assumption 4), so continue could not rebuild it even if it tried.
- **`prune --confirm` re-scans** (review item 2): `prune_records` (`session_delegation_control.py:99-116`) cancels
  whatever is stale at confirm time, including records that became stale after the preview.
- **No reason is recorded** (5g): `advance` and `prune_stale` update `state` and `updated_at` only; `pruned-stale` and
  every other evidence string are checked, then dropped.
- **Pre-flight matching** (5f): `_matches_rule` (`session_delegation_claude.py:209`) knows exact names and `prefix*`,
  not the server-level rule `mcp__agent-relay`, which Claude Code honours; pre-flight then reports a missing allow the
  session actually has (conservative, but inconsistent).
- **Dead code** (5j): the `plan` and `dontAsk` branches of `_permission_shape` (lines 227–231) served `host-native`,
  removed in 0.6.0.
- **Scope hook gaps** (5i): a Glob with both `path` and a `pattern` only checks `path`, so `path: docs`,
  `pattern: ../other.txt` or an absolute pattern is not checked; a project setting `disableAllHooks: true` may switch
  the hook off.
- Delegation store: `SCHEMA_VERSION = 2`, no migration path (`session_delegation.py:30`, 473–505).

## Assumptions (accepted by the user 2026-10-09)

1. **Store schema 3.** The store gains two nullable columns, `scope` (JSON list) and `state_reason` (text), through an
   additive in-place migration 2 → 3 (`ALTER TABLE … ADD COLUMN` under the write lock, then `user_version = 3`). It is
   the store's first migration. A 0.6.0 plugin refuses a schema-3 store, so going back to 0.6.0 after using 0.6.1 needs
   the delegation store restored from the copy the migration leaves next to it. Alternative rejected: refusing every
   continue of a Claude review (no schema change), because then no reviewer could ever be asked a follow-up.
2. **Continue repeats the launch shape.** A Claude continue passes the same limits as create: the same
   `--mcp-config` file, `--strict-mcp-config`, `--setting-sources`, `--permission-mode`, `--permission-prompts none`,
   `--disable-slash-commands` (unless user environment), `--no-chrome`, `--tools`, and the scope hook when the record
   has a scope. All of it is derived from the stored intent, `host_permission` and `scope`; one function builds the
   shared part for both commands, so they cannot drift again.
3. **Old records.** A Claude record created before schema 3 has `scope = NULL` (unknown). Continuing a `safe-review`
   with an unknown scope is refused (`scope-unknown`, next step: create a new review); a `bounded-development` record
   continues with the repeated launch shape and no scope (a development task never had one).
4. **`prune --confirm <id,…>`.** `--confirm` takes the ids printed by the preview (6-character prefixes, as shown) and
   cancels exactly those that are still stale and not live; ids that are no longer stale, unknown or ambiguous are
   reported as skipped, not cancelled. `--confirm` without ids is an error. `--include-unknown-hosts` keeps its meaning.
5. **Reasons are stored.** Every state change writes its evidence (e.g. `pruned-stale`, `host-cancelled`) to
   `state_reason`; `status` and `prune` show it.
6. **`_matches_rule`** also accepts the server-level rule (`mcp__<server>` and `mcp__<server>__*`) for that server's
   tools, as Claude Code does.
7. **Dead branches** of `_permission_shape` are removed; an unknown intent still raises.
8. **Scope hook.** Glob checks `path` and the pattern's directory part (relative to `path`, or absolute); any `..` that
   leaves the scope is denied. The generated `--settings` also sets `"disableAllHooks": false`, if the real check
   shows that flag settings override the project's `disableAllHooks: true`; if they do not, the launch refuses a
   scoped review in such a project (`scope-hook-disabled`) instead of starting it without the hard limit.
9. **Codex continue** is checked, not assumed: the plan reads `session_delegation_codex.py` continue and records whether
   the turn keeps the thread's sandbox and approval; a gap found there is fixed here.

## Decisions

- **D171 continue keeps the limits.** Assumptions 2, 3 and 9.
- **D172 store schema 3.** Assumptions 1 and 5.
- **D173 prune confirms by id.** Assumption 4.
- **D174 pre-flight and hook accuracy.** Assumptions 6, 7 and 8.

## Requirements

1. Red first: a Claude continue argv contains the same limit flags as the create argv for the same record (both
   intents, with and without user environment, with and without scope); removing the create-only parts (`--name`) of
   the create argv equals the continue argv apart from `--resume <session>`.
2. Red first: a 0.6.0-shaped (schema 2) store opens as schema 3 with records intact and `scope`/`state_reason` NULL; a
   second open is a no-op; a migration interrupted before `user_version = 3` re-runs cleanly; a pre-schema-3
   `safe-review` continue is refused `scope-unknown` and touches no host.
3. Red first: `prune --confirm <ids>` cancels only listed ids; a record that became stale after the preview is left;
   `--confirm` with no ids fails; a second run finds none; `state_reason = pruned-stale`.
4. Red first: `_matches_rule("mcp__agent-relay", "mcp__agent-relay__bridge_send")` is true; the dead branches are gone.
5. Red first: the hook denies Glob `{path: "docs", pattern: "../other.txt"}` and an absolute pattern outside the
   scope; the `disableAllHooks` behaviour per assumption 8.
6. Real check on this Mac: a scoped Claude review continued once still answers DENIED for a file outside the scope.
7. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Always: limits only narrow; previews before any `--confirm`.
- Ask first: any further schema change; deleting delegation records.
- Never: continue a scoped review without its scope; run `prune --confirm` on the user's records without their yes.

## Acceptance (coordinator, after 0.6.1 — not done here)

- A continued Codex → Claude Code review keeps its permission mode, tools and scope (review item 1, measured on the
  real host).
- B1: Codex's first create succeeds on the real host.
- `prune` preview, then `--confirm <ids>` on the three stuck records with the user's yes.

## Open questions

None. Accepted by the user on 2026-10-09 (reviewed by the round-2 coordinator, 72600fc).
