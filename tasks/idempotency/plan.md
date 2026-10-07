# Plan: idempotency

Based on [`spec/idempotency.md`](../../spec/idempotency.md) (accepted by the user on 2026-10-07, including schema v4
and D33–D36). Branch `claude/idempotency` from main 0d668fe. Every bridge change updates `UPSTREAM.md` and
`UPSTREAM.sha256` (`scripts/bridge-manifest.py`) in the same commit; red → green each task.

## Task List

### Task 1: Key check (D33, D34, assumptions 1, 2, 5)
In `insertMessage`, a stored row with the same sender and key is compared on recipient, body and thread (`replyTo`
joins in Task 3); a difference throws `IdempotencyConflictError` (key, stored id and delivery state, differing fields, "already
stored and in delivery; no resend needed") unless the sender is `bridge`. `send()` reports whether the message was newly stored; `bridge_send` adds `duplicate: true` and the
warning, and no new wake job is queued (already true: `enqueue` is skipped on the early return — pinned by a test).
The duplicate return stays before the pending-cap check. Tests: identical retry, each differing field refused,
delivery options ignored, bridge notices folded, retry at the cap. Upstream test `bridge-store.test.ts:60` keeps
passing. **Files:** `src/bridge-store.ts`, `src/server.ts`, new `test/idempotency.test.ts`.

### Task 2: Schema v4 and Python readers (assumption 3)
v4 migration adds nullable `messages.reply_to INTEGER`; old-process INSERTs still work; `MAILBOX_SCHEMA_VERSIONS =
(2, 3, 4)` with Python tests on a v4 fixture; `relay_status.py` unchanged. v2 fixture → v4 in one open with the pre-migration backup; `upgrade --confirm`
test from a v2 runtime ends at v4 with counts intact (round 2 upgrades this Mac from v2). **Files:** `src/schema.ts`,
`test/schema.test.ts`, `hooks/native_collaboration_runtime.py`, Python tests.

### Checkpoint (report): key check and schema green

### Task 2b: Delegation result route (coordinator, 2026-10-07)
One line in the result-route instruction (`session_delegation_control.py` `_with_result_route`) and the
session-delegation skill: a "same key, different content" refusal means the result is already delivered — do not
retry or report failure. Controller-side test: a reworded retry leaves one result message and result delivery
unchanged. **Files:** `hooks/session_delegation_control.py`, its tests, `skills/*delegation*/SKILL.md`.

### Task 3: Reply link (assumption 3, D36)
`bridge_send` `replyTo`: the original must exist; thread inherited when omitted, a different thread refused;
`replyTo` part of the key comparison; `BridgeMessage.replyTo` shown in send result, inbox, thread and outbox; outbox
lists reply ids per sent message. **Files:** `src/bridge-store.ts`, `src/server.ts`, `test/idempotency.test.ts`.

### Task 4: Reply de-duplication (D35)
Same sender, `replyTo`, recipient and body → the earlier reply returned as a duplicate, unless it ended `failed` or
`expired`; inside the send transaction after the key check. Tests: dedup, re-send after `expired` and after
`failed`, two stores on one file racing → one message.

### Task 5: Docs
README, `bridge_send` description, interface rows 45, 75, 79, 103, 118 and gap f, checklist D14 wording,
`UPSTREAM.md` change table; upgrade note that the runtime upgrade now migrates to v4.

### Task 6: Live D14 (temporary `AGENT_RELAY_HOME`, coordinator told first)
Runtime from this branch; send twice with one key (one message, `duplicate: true`), then a different body with that
key (refused); a reply with `replyTo` sent twice (one message, thread inherited). No host config change.

### Checkpoint (gate): module review
