# Spec: delegation-cross-host

## Objective

The user's scope for delegation (round 2, 2026-10-09): agent-relay's delegation is the fallback when the delegate
plugin is not installed, and it must work. It keeps exactly two directions, Claude Code → Codex and Codex → Claude
Code; same-host delegation (Claude → Claude, Codex → Codex) is no longer offered.

Round-2 findings in scope:

- **B1.** From Codex, the first `create` always fails: writing the state under `~/.agent-relay` from Codex's default
  sandbox raises `sqlite3.OperationalError: attempt to write a readonly database` (`session_delegation.py:568`,
  `authorize`); it succeeds only when retried.
- **B6.** With the delegate plugin installed, "派 Codex 审查/执行" may trigger both plugins.
- The same-host branch never returned results to the origin (round-2 B1 of the first list, now closed by removing
  same-host delegation).

Readers: the user; the round-2 coordinator (acceptance after the batch).

## What exists today (main 9037f48, 2026-10-09)

- `session_delegation.py:33` `PERMISSION_INTENTS` includes `host-native`; `authorize` (:218-236) accepts any
  `target_hosts` among `HOSTS`, including the origin's own host. Both adapters refuse `host-native` when it reaches
  them (`session_delegation_claude.py:208`, `session_delegation_codex.py:533`: `host-native-permission-unsupported`),
  so that intent never produced a session.
- `session_delegation_control.py`: `_route` (:256) builds no result route when origin and target host are the same;
  `_routing_outcome` (:276-299) reports `transport: host-native-<host>`, `routeReason: same-host-native`; delivery is
  skipped for same-host at :388 and :522; the CLI offers `--permission host-native` (:735, :749).
- `skills/session-delegation/SKILL.md`: documents `host-native` and same-host results; no mention of the delegate
  plugin; tells Codex to run `session_delegation_control.py` with no word about the sandbox.
- Codex's default sandbox lets a command write its workspace (and temporary directories) only; `~/.agent-relay` is
  outside it.

## Assumptions (accepted by the user 2026-10-09)

1. Same-host requests are refused at authorization with a clear reason; an existing same-host record from an older
   version can still be listed, shown and cancelled, never continued.
2. `host-native` is removed from new requests (it never worked: both adapters refuse it). Stored rows that carry it
   stay readable. This narrows accepted input: part of the 2.0 batch.
3. B1 is solved in two places: (a) the skill tells a Codex session to run the state-writing commands (`create`,
   `continue`, `cancel`) with the host's sandbox escalation requested up front, so the first attempt asks the user once
   instead of failing; (b) when the state cannot be written anyway, the controller answers with a clear code
   (`state-not-writable`, what to do next) instead of a traceback. The exact escalation wording is checked against a
   real Codex in the acceptance.
4. B6 is a skill rule in Claude Code: if the session has the delegate plugin's `delegate:delegate` skill, "派给 Codex
   审查/执行" requests go there and agent-relay's session-delegation does not start; without it, agent-relay takes them.
   Codex has no delegate plugin, so Codex → Claude Code always uses agent-relay.
5. Acceptance (coordinator, real projects, without the delegate plugin): Claude Code → Codex and Codex → Claude Code
   are each created with one sentence and return their result to the origin's mailbox; `continue` keeps working.

## Decisions

- **D158 cross-host only.** `authorize` rejects a request whose `target_hosts` contains the origin's host
  (`same-host-unsupported`, with a sentence naming the two supported directions); `create` and `continue` refuse a
  same-host claim the same way. The same-host routing outcome stays only to describe old records.
- **D159 no `host-native` intent.** Removed from `PERMISSION_INTENTS` for new requests, from the CLI choices and from
  the skill; rows stored with it are still validated and shown as they are.
- **D160 Codex writes its state on the first try.** The skill's Codex steps run `create`, `continue` and `cancel` with
  the sandbox escalation requested up front (read-only `permissions`, `list` and `status` run in the sandbox). The
  controller maps a read-only or unwritable state database to `state-not-writable` with the next step, never a
  traceback.
- **D161 the delegate plugin goes first.** session-delegation's description and body say: in Claude Code, when the
  `delegate:delegate` skill is available, requests to hand work to Codex go there; agent-relay's delegation is the
  fallback when it is not, and the only path for Codex → Claude Code.

## Requirements

1. Red first: `authorize` with the origin's host among the targets is rejected (`same-host-unsupported`) for both hosts;
   cross-host requests still pass; `host-native` is rejected as an unknown intent; an old row with `host-native` and a
   same-host target still loads, lists and cancels; `continue` on it is refused.
2. Red first: a controller command whose state database is read-only returns `state-not-writable` with a next step and
   exit code 1, with no traceback (simulated with a read-only state directory).
3. Skill: same-host and `host-native` text removed; the Codex sandbox step (D160); the delegate rule (D161); skill tests
   updated. README and CHANGELOG `[Unreleased]` (breaking: same-host delegation and `host-native` removed).
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.
5. Acceptance as assumption 5, plus: from Codex, the first `create` asks once for escalation and succeeds.

## Boundaries

- Always: delegation stays bounded (safe-review / bounded-development, explicit counts and expiry).
- Ask first: deleting stored delegation records; changing the result route.
- Never: create a same-host session; widen a session's permissions; run the state-writing commands outside the
  sandbox without the host asking the user.

## Success criteria

Delegation offers exactly the two cross-host directions; a Codex session creates a Claude Code session on its first
attempt (after one escalation prompt); in Claude Code the delegate plugin wins when present; results come back to the
origin in both directions.

## Open questions

None. Accepted by the user on 2026-10-09 (assumptions 1–5, D158–D161).
