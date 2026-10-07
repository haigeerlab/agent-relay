# Spec: idempotency

## Objective

Make a retry key mean one message: a retry with the same key and the same content returns the stored message and says
it was not sent again; the same key with different content is refused instead of silently returning the old message.
Let a reply name the message it answers, and de-duplicate a repeated identical reply to the same message. Interface
gap f (rows 75, 79, 103, 118); checklist D14.

Readers: the user; the round 1 coordinator (D14); agents building `identity-check` (it adds "only the recipient may
reply" on top of the reply link made here).

## What exists today (measured in the vendored bridge after durable-ordering, main 0d668fe, 2026-10-07)

- `bridge_send` takes an optional `idempotencyKey`; `messages` has a unique index on `(from_agent, idempotency_key)`
  (`schema.ts:36-38`). Inside the send transaction, a stored row with the same sender and key is returned as is, with
  no comparison of recipient, body or thread and no sign that nothing new was stored (`bridge-store.ts:395-400`).
  `test/bridge-store.test.ts:60` pins only the identical-retry case.
- The bridge's own senders rely on the silent return: failure notices use one key per sender, recipient and 30-minute
  window, so a second failure in the window (different body) is folded into the first (`notices.ts:78`); retirement
  notices (`lifecycle.ts:52`) and Codex round results (`orchestrator.ts:816`) also use fixed keys.
- The delegation result route tells the target session to call `bridge_send` "exactly once" with a derived key
  (`session_delegation_control.py:228-239`); a retry by that session after a lost response today returns the stored
  result silently.
- There is no reply field: a reply is an ordinary send on the same `threadId`, and nothing records which message was
  answered (interface rows 79, 103).
- Schema version 3; the Python readers accept `MAILBOX_SCHEMA_VERSIONS = (2, 3)` (`native_collaboration_runtime.py:23`).

## Assumptions

Confirmed by the user on 2026-10-07, including schema v4.

1. **Same content** means same recipient, body, thread and reply link (assumption 3). Delivery options (`wake`,
   `expiresInSeconds`, `allowUnregistered`) are not content: a retry that changes them still returns the stored
   message unchanged.
2. **A key is permanent:** no key reuse after expiry or failure, as today (the unique index stays). A sender that wants
   to re-send uses a new key.
3. **Reply link is stored:** `bridge_send` gains an optional `replyTo` (message id). Schema v4 adds a nullable
   `messages.reply_to` column — an additive migration like v3, taken by the existing `upgrade --confirm`; the Python
   readers accept v2, v3 and v4. `replyTo` must name an existing message; `bridge_inbox`, `bridge_thread`,
   `bridge_outbox` and `bridge_send` show `replyTo`, and `bridge_outbox` shows for each sent message the ids of its
   replies (row 103, "message replied").
4. **Who may reply is not checked here.** "Only the recipient may reply" (gap g) needs a verified sender and belongs to
   `identity-check`; this module only checks the original exists.
5. **The bridge's own notices are exempt** from the different-content refusal and keep today's silent return, because
   folding notices by key is deliberate (`fromAgent === "bridge"`, the same exemption as the pending cap).
6. No change to `relay_status.py` output or its `ready` rule; `interface.json` stays 1.0.

## Decisions

D33–D36 accepted on 2026-10-07.

- **D33 refuse a reused key with different content** with an error naming the key, the stored message id and which
  fields differ; nothing is stored or pinged. Alternative: keep returning the old message but add a warning.
- **D34 a duplicate is visible:** when a send returns an already stored message (same key, or a de-duplicated reply),
  the result carries `duplicate: true` and a warning "already stored as message N; not sent again", and no new ping
  is queued.
- **D35 reply de-duplication:** a send with `replyTo` from the same sender, to the same recipient, with the same body
  returns the earlier reply (D34) — unless that earlier reply ended `failed` or `expired`, in which case a new message
  is stored, so a reply that never arrived can be sent again. Checked in the send transaction, after the key check.
- **D36 thread follows the original:** a reply without `threadId` takes the original's thread; a reply whose
  `threadId` differs from the original's is refused. Alternative: no thread rule.

## Requirements

1. Key check per D33 and D34, with tests: identical retry → same id, `duplicate: true`, no second wake job;
   different body, recipient, thread or `replyTo` each refused; delivery options ignored; bridge notices still folded.
2. Schema v4 (`reply_to`), old-process INSERTs still work; Python readers accept 2–4 with tests.
3. `replyTo` per assumption 3 and D36: unknown id refused; thread inherited or mismatch refused; shown in inbox,
   thread, outbox and the send result; outbox lists reply ids.
4. Reply de-duplication per D35 with tests, including re-send after the earlier reply `expired` and `failed`, and two
   stores on one file racing the same reply → one message.
5. Pending cap unchanged in order: a duplicate return happens before the cap check (a retry of a stored message still
   succeeds at the cap).
6. `UPSTREAM.md` / `UPSTREAM.sha256`, README, tool descriptions, interface rows 45, 75, 79, 103, 118 and gap f, and
   checklist D14 updated.

## Testing strategy

TS unit tests in the bridge (`validate.sh` runs them); Python tests for the v4 readers. Live (temporary
`AGENT_RELAY_HOME`, no host config change, round 1 coordinator told first): D14 — send twice with one key, then a
different body with that key; a reply with `replyTo` sent twice.

## Boundaries

- Always: additive migration; keep persist-before-submit and the never-replay rule; keep history.
- Ask first: changing `interface.json`; letting keys be reused; any host config change.
- Never: delete or rewrite a stored message; push without approval.

## Success criteria

1. All tests green, including the refusal, duplicate, reply and race tests.
2. Live D14 passes against the target column.
3. Docs updated.

## Open questions

None.
