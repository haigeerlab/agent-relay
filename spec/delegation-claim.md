# Spec: delegation-claim

## Objective

Session delegation starts Claude Code or Codex sessions and turns on the user's behalf. The 0.4.0 architecture review
found that neither the create nor the follow-up path claims the operation before its external side effect, and reading
the code for this module confirmed both, for both adapters:

- **Create.** `claim_launch` inserts a `creating` row, but a second call with the same launch key gets the same row back,
  still `creating`; the controller only stops early when the state is *not* `creating`, so both calls reach
  `adapter.create`. Codex sends `thread/start` twice; the second fails only at `bind_host`, after its thread exists.
- **Follow-up.** The adapters check `state == "completed"` outside any transaction, send the turn (`turn/start`, or the
  Claude resume command), and only then move `completed → running` in `begin_follow_up`. Two concurrent continues both
  start a turn; the later one fails after its turn started.

A duplicate session or turn is a side effect the user sees (and pays for). The user chose (2026-10-08) to fix this as
the next remaining review finding.

Readers: the user; the round-2 coordinator, who reviews the PR before the user merges.

## What exists today (main 842b672, 2026-10-08)

- `hooks/session_delegation_control.py:345-394` `authorize_and_create`: `store.authorize` → `store.claim_launch` →
  if the claim is not `creating`, return; else `adapter.create(...)`. `:452-483` `continue_named`: resolve, require an
  active authorization, `adapter.continue_turn(...)`. `:485-519` status and cancel call the adapter without a claim.
  The CLI prints the public JSON and exits 0, or `{"state": "error", "reason": …}` and exits 1 (`:795-812`).
- `hooks/session_delegation.py:611-675` `claim_launch` (`BEGIN IMMEDIATE`, idempotent on the launch key);
  `:806-836` `begin_follow_up` (`completed → running`, under `BEGIN IMMEDIATE`, after the turn was sent);
  `:746-775` `record_host_unknown` (`creating|unknown → unknown`); `_TRANSITIONS` (`:40-48`) allows
  `completed → unknown` and `running → unknown`. Schema version 2; a different version is refused (`:479`).
- `hooks/session_delegation_codex.py:690-750` `create` (`thread/start` → `bind_host` → `turn/start` → wait),
  `:752-810` `continue_turn` (`thread/resume` → `turn/start` → `begin_follow_up` → wait).
  `hooks/session_delegation_claude.py:555-597` `create` (runs the Claude launch command), `:649-` `continue_turn`.
- `DelegationStore.root` is the delegation directory (`~/.agent-relay/delegation`).
- Docs listing public prerequisites: `skills/session-delegation/SKILL.md:45-58`, `docs/collaboration-interface.md`
  §delegation rows (`:159-162`).

## Assumptions (accepted by the user 2026-10-08)

1. One lock file per delegation, `<delegation dir>/claims/<delegation id>.lock` (0600, directory 0700), held with an
   exclusive `fcntl.flock`; the kernel releases it if the holder dies. The delegation database stays at schema 2 (a
   new column or state would need schema 3, which an older plugin refuses, breaking a plugin rollback).
2. The claim is taken in the controller, which both hosts go through: around `adapter.create` (after `claim_launch`)
   and around `adapter.continue_turn`. Status and cancel take no claim and behave as today.
3. A call that cannot take the claim does not call the adapter; it returns the delegation's current state with
   `prerequisite: "operation-in-progress"` (another call is working on it).
4. Before calling the adapter the controller writes the operation (`create` or `continue`) into the lock file and
   fsyncs it; after the adapter returns or raises, it empties the file. A holder that finds the file non-empty knows
   the previous holder died mid-operation, so the host may have been reached: a `creating` row is recorded `unknown`,
   a `completed` or `running` row is advanced to `unknown`, and the call returns `unknown` with
   `prerequisite: "previous-operation-interrupted"`, never launching again; `status` then reconciles as today.
5. When the host was clearly not reached (`held`), the claim is released with the call and a retry may proceed.
6. `interface.json` stays 1.4 (delegation output is read only by agent-relay's own skills, not by Spec Guard); the two
   new prerequisite values go into the session-delegation skill and the interface doc.
7. Hooks only, no bridge change; on the real host it takes effect when the plugin updates, no runtime upgrade.
8. Red first: two processes creating or continuing the same delegation → the adapter is called once, the other gets
   `operation-in-progress`; a lock file left non-empty → the next call returns `unknown` /
   `previous-operation-interrupted` without calling the adapter; after `held` a retry proceeds; existing delegation
   tests stay green; validate on Python 3.9, 3.10, 3.14.
9. The live check uses a temporary HOME, two real processes and a fake host backend; no real Claude or Codex session
   is started.
10. The round-2 coordinator reviews the PR; the user merges after every CI check has finished green.

## Decisions

- **D122 claim file.** New `session_delegation.OperationClaim` (context manager) opens
  `<store.root>/claims/<delegation_id>.lock` (creating the directory 0700 and the file 0600 with `O_NOFOLLOW`; a
  symlink or a non-regular file is refused with `DelegationError("claim-file-unsafe")`), takes
  `flock(LOCK_EX | LOCK_NB)`; `BlockingIOError` → `OperationBusy`. `previous()` returns the leftover operation text
  (empty string when clean); `begin(operation)` truncates, writes the word and fsyncs; `end()` truncates and fsyncs.
  The file is never deleted (it holds no state when empty).
- **D123 controller.** `authorize_and_create`, after `claim_launch` returns a `creating` claim, and `continue_named`,
  after resolving and the active check, run the adapter call inside `OperationClaim`: busy → `_public(current, …,
  prerequisite="operation-in-progress", host_operation=…)` without calling the adapter; a leftover operation → D124;
  else `begin(...)`, call the adapter, and `end()` in a `finally` (an exception from the adapter still empties the
  file: the adapters record `unknown` themselves when the host may have been reached).
- **D124 interrupted operation.** With a leftover operation: `creating` → `store.record_host_unknown(id)`;
  `completed` or `running` → `store.advance(id, "unknown", "host-result-unknown")`; any other state is left as it is.
  Then `end()` (the interruption is now recorded in the database) and return `_public(current, …, state="unknown",
  prerequisite="previous-operation-interrupted", host_operation=…)`. No adapter call.
- **D125 CLI.** Both new results are ordinary public JSON with exit 0, like `held`.
- **D126 docs.** Session-delegation skill: `operation-in-progress` (another call is creating or continuing this
  session; wait and check `status`, do not retry in a loop) and `previous-operation-interrupted` (a previous call
  stopped half way; the host may have a session or turn; use `status`, never create again by name). Interface doc
  delegation rows; CHANGELOG `[Unreleased]`.

## Requirements

0. Red first (new `hooks/test_delegation_claim.py`, temporary state root, fake adapter):
   - a create and a continue each, while a second process (or a second descriptor) holds the claim → the adapter is
     not called, `prerequisite` `operation-in-progress`, state unchanged;
   - two real processes creating the same launch key at once with a fake adapter that blocks → the adapter runs
     exactly once in total;
   - a lock file left with `create` (row `creating`) → `unknown` row, result `unknown` /
     `previous-operation-interrupted`, adapter not called, file empty afterwards; the same with `continue` on a
     `completed` row;
   - an adapter returning `held` → the file is empty and a second create proceeds; an adapter raising → the file is
     empty;
   - a symlinked lock file is refused.
1. Every existing `test_session_delegation*.py` stays green unchanged.
2. Validate on Python 3.9, 3.10, 3.14; CI green (all checks finished).
3. Live check in a temporary HOME with the CLI and a fake backend: two concurrent `create` processes → one launch;
   a planted leftover operation → `previous-operation-interrupted`. No real host session.

## Boundaries

- Always: temporary state roots in tests; claim before any adapter call that may reach a host.
- Ask first: the real `~/.agent-relay/delegation`; starting any real Claude or Codex session.
- Never: change the delegation schema; launch again after an interrupted operation; merge before the round-2
  coordinator's review and finished CI.

## Success criteria

No two calls can reach a host for the same delegation at the same time, and a call that died mid-operation is never
silently retried: the next call reports it and leaves reconciliation to `status`.

## Open questions

None. Assumptions 1–10 accepted on 2026-10-08 ("成立"); the spec (D122–D126) accepted on 2026-10-08 ("接受").
