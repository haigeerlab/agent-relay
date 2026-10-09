# Spec: delegation-hygiene

## Objective

The last module of the round-2 batch (0.6.0). Round-2 findings:

- **B4.** A delegated read-only review asked to "review only README.md" also read `.gitignore` and Claude's local
  config in its first turn. The user accepted a soft limit (scope in the constraints, files read listed in the result)
  and asked whether the Claude side can be a hard limit.
- **B5.** The name the user gives (`pwa-cc`) is registered with a random suffix (`pwa-cc-<8>`), so contacting it by name
  needs fuzzy matching; three old records are stuck in `creating`/`unknown` (`sg-dl-claude 27f0de`,
  `ar-acc-r1fix-c7b d1e1cf`, `ar-acc-r1fix-diag`) with no way to clear them.
- **Interface 2.0.** The batch is breaking; `interface.json` moves to 2.0 here, last (wake-any-mode D145). Spec Guard
  0.56.0 is released and accepts `>=1.0,<3.0` (the coordinator, 2026-10-09).

Readers: the user; the round-2 coordinator (acceptance after the batch); Spec Guard (interface version only).

## What exists today (main b634c16, 2026-10-09)

- The task prompt reaches the delegated session inside a control envelope (`_bounded_prompt`, `_with_result_route`);
  there is no scope parameter.
- Measured on this Mac (Claude Code 2.1.295, 2026-10-09, `claude -p --model haiku --permission-mode dontAsk --tools Read
  --setting-sources project,local --strict-mcp-config`, a project with `README.md` and `other.txt`):
  - allow only `Read(README.md)` via `--settings`: **both files were read** — in `dontAsk`, reading inside the project
    needs no allow, so an allow list cannot narrow it;
  - a `PreToolUse` hook for `Read|Grep|Glob` passed through `--settings` that denies paths outside the scope:
    `other.txt` **DENIED**, `README.md` read. The hook applies even with `--setting-sources project,local`.
- Internal mailbox name of a Claude delegation: `_internal_name(friendly, id) = friendly[:110] + "-" + id[:8]`; the
  friendly name is stored (`friendly_name`).
- Delegation states: `creating` and `unknown` may move to `cancelled` (`session_delegation.py` `_TRANSITIONS`).
- `interface.json` declares `1.4`; `relay_status.py`'s docstring keeps the version history; the interface document
  states Spec Guard's required range in §1, §11 and §12.

## Assumptions (accepted by the user 2026-10-09)

1. `create --scope <path>` (repeatable; project-relative; each must exist inside the project) is for `safe-review` only;
   a development request with a scope is refused (`scope-review-only`), because Bash would read past any limit.
2. Scope reaches the session in the control envelope (both hosts): review only these paths; end the result with
   "Files read:" and every file actually read. On Codex this is the whole limit (soft).
3. On Claude Code targets the scope is also a hard limit: the launch adds a `PreToolUse` hook (an agent-relay script,
   passed with `--settings`) that denies Read, Grep and Glob outside the scope, comparing real paths (symlinks resolved).
   A Grep or Glob without a path searches the project root and is denied unless the scope covers it.
4. The scope is chosen at `create` and lives in the launched session; it is not stored in the delegation database (no
   schema change). A held create retried by the user uses the scope given on that retry.
5. A delegated session can be named by its friendly name: session-routing resolves a name that matches no mailbox
   agent exactly against active delegations' friendly names (read only), uses it when exactly one matches, and asks
   when several do.
6. Cleanup: `session_delegation_control.py prune` lists, read only, the records in `creating` or `unknown` with no
   live host session that have not changed for an hour; `prune --confirm` moves exactly those to `cancelled` (reason
   `pruned-stale`), touches no host and deletes nothing. Running it on the user's own records is the user's call.
7. Interface 2.0: only `"interface"` changes in `interface.json`; the `status` command and its `{ready, setup}` output
   stay exactly as they are (as promised to Spec Guard). The interface document's version and required range move to
   2.0 and `>=1.0,<3.0`.

## Decisions

- **D166 review scope.** As assumptions 1, 2 and 4.
- **D167 hard limit on Claude Code.** As assumption 3: `hooks/delegation_scope_hook.py`, given the project root and the
  scope list, answers `permissionDecision: deny` with the reason "outside the review scope" for any Read/Grep/Glob
  target outside it; the launch is otherwise unchanged.
- **D168 the friendly name is an alias.** As assumption 5.
- **D169 prune stuck records.** As assumption 6.
- **D170 interface 2.0.** As assumption 7; CHANGELOG lists the batch's breaking changes under 2.0.

## Requirements

1. Red first: `--scope` validation (inside the project, exists, safe-review only); the envelope text carries the scope
   and the "Files read:" instruction.
2. Red first: the hook script on fixture events — inside the scope allowed; outside denied; a symlink inside the scope
   pointing outside denied; Grep/Glob without a path denied unless the scope covers the root; malformed input denied.
   The Claude launch with a scope carries exactly one `--settings` with that hook; without a scope the argv is unchanged.
3. Red first: routing resolves a friendly name to the one active delegation's mailbox name, asks on several, leaves
   exact mailbox names as today.
4. Red first: `prune` preview lists only stale `creating`/`unknown` records without a live host; `--confirm` cancels
   exactly those and nothing else; a second run finds none.
5. `interface.json` 2.0 with `status` unchanged (`test_packaging`); interface document; README, skills, CHANGELOG.
6. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.
7. Acceptance (coordinator, after the batch): a Codex → Claude Code review scoped to `README.md` reads nothing else and
   lists the files it read; `告诉 <friendly name>` reaches the delegated session; `prune` clears the three stuck records
   after the user confirms; Spec Guard 0.56.0 reports agent-relay `ready` with interface 2.0.

## Boundaries

- Always: scope limits only narrow; previews before any `--confirm`.
- Ask first: deleting delegation records; changing `interface.json` beyond the version string or the status contract.
- Never: run `prune --confirm` on the user's records without their explicit yes; widen what a session may read.

## Success criteria

A scoped Claude Code review cannot read outside its scope and reports what it read; Codex reviews get the same
instruction; users reach delegated sessions by the name they gave; stuck records can be cleared on purpose;
agent-relay 0.6.0 declares interface 2.0 and Spec Guard accepts it.

## Open questions

None. Accepted by the user on 2026-10-09 (assumptions 1–7, D166–D170).
