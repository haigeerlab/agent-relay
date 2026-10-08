# Spec: inbox-read-receipt

## Objective

Reading another identity's mailbox changes that identity's delivery state. `bridge_inbox` and `bridge_wait` (with
`acknowledge: false`) record every listed message as read for the named agent whoever calls them, and
`bridge_inbox`, `bridge_wait` and `bridge_outbox` refresh the named agent's activity. Recording a read is not cosmetic:
the message moves to `accepted`, and a still-pending wake job for it is closed as `read`, so **the real recipient is
never pinged for it**. Found by the 0.4.0 architecture review (C2); the user decided (2026-10-08) to keep reads
unauthenticated (threat model "one user, one Mac", `spec/identity-check.md:46`) but to record a read only when the
caller is the identity itself, and to tell a bystander that its read was not recorded (a new result field, interface
1.4). Third module of 0.5.0.

The interface document already says a wake job moves to `read` "when the recipient fetches it"
(`docs/collaboration-interface.md:101`); this module makes the code match and states who the recipient is.

Readers: the user; the round-2 coordinator, who reviews the PR before the user merges it (agreed 2026-10-08) and checks
Spec Guard against interface 1.4.

## What exists today (main 5c557eb, 2026-10-08)

- `bridge/src/server.ts:355-359` `bridge_inbox`: no identity check; `store.wakes.recordRead(agent, ids)` and
  `store.touch(agent)` for any caller.
- `server.ts:392-405` `bridge_wait`: `caller.require` only when `acknowledge` is true (D37); `store.touch(agent)` and
  `recordRead(agent, ids)` for any caller otherwise.
- `server.ts:492-493` `bridge_outbox`: `store.touch(agent)` for any caller.
- `wake-queue.ts:155-170` `recordRead`: sets `messages.read_at` (delivery state `accepted`, follow `read`) and moves a
  `sending` / `unknown` / `held` / `accepted` wake job to `read`; `claimStep` (`:193-196`) closes a `pending` job whose
  message has `read_at` as `read` without pinging.
- `claimStep` claims only `pending` jobs; once a ping is `accepted` the job is never claimed again, whatever happens to
  `read_at` later.
- `bridge-store.ts:638` `touch` sets `agents.last_seen`, which feeds `lastActivity` and the "recipient looks idle"
  send warning (`addressing.ts:110`).
- `identity.ts` `CallerIdentity.owns(name, agent)`: with a verified caller host (Claude sets the session in the
  environment) the recorded host decides, which survives a bridge restart; without one (Codex: the app-server does not
  expose the thread) only a name registered through this bridge process counts. A host claimed with `host:` is never
  proof (acceptance-030-gaps D75a).
- `interface.json` `1.3`; `test_packaging.py:36` pins it.

## Assumptions (accepted by the user 2026-10-08)

1. "The identity itself" is `CallerIdentity.owns` (identity-check D37): Claude by its verified session against the
   recorded host (unaffected by a bridge restart); Codex only when registered through the current bridge process; a
   claimed `host` does not count.
2. Changed: `bridge_inbox` and `bridge_wait` with `acknowledge: false` record the read and refresh activity only for
   the identity itself; `bridge_outbox` refreshes activity only for it (it never recorded reads). `bridge_wait` with
   `acknowledge: true` already requires the identity and is unchanged.
3. New result fields on `bridge_inbox` and `bridge_wait`: `readRecorded` (boolean, always present) and, when it is
   false, `readNote` (string) saying the read did not change delivery, the recipient will still be pinged, and, if
   this is the caller's own name, to call `bridge_register` again from this session. `bridge_outbox` gets no field.
4. Interface 1.4 (an addition): `interface.json`, the interface document (§2.1 rows and the "Message read" row: only
   the recipient's own read counts), the packaging test. Spec Guard's range `>=1.0,<2.0` is unchanged; the round-2
   coordinator confirms it.
5. Wake bound: one message gets at most one successful ping, whatever reads happen; a read that is not recorded can
   at most let one still-`pending` message be pinged once although its own recipient already saw it (the Codex
   restart case). Never repeated pings.
6. Reads stay unauthenticated; schema unchanged.
7. Tests red first; validate on Python 3.9, 3.10, 3.14; a live check with two MCP clients (bystander and owner)
   comparing `deliveryState` and the wake job before and after each read; after the PR opens, the round-2 coordinator
   reviews before the user merges.

## Decisions

- **D99 who records a read.** In `bridge_inbox` and in `bridge_wait` with `acknowledge: false`, `recordRead` and
  `touch` run only when `caller.owns(agent, store.getAgent(agent))`; `bridge_outbox` calls `touch` only then. The
  listing itself is unchanged for everyone.
- **D100 the fields.** `readRecorded: true | false` on every `bridge_inbox` and `bridge_wait` result (also when the
  page is empty). When false, `readNote`:
  `"This read was not recorded: \"<agent>\" is not an identity of this session, so its messages stay unread for delivery and its recipient will still be pinged. If \"<agent>\" is this session's own name (for example after the bridge restarted), call bridge_register with it from this session again."`
  The tool descriptions mention both fields.
- **D101 interface 1.4.** `interface.json` `1.4`; `collaboration-interface.md` §2.1 rows for `bridge_inbox` /
  `bridge_wait` list `readRecorded` / `readNote` (1.4), the "Message read" row says only the recipient's own read
  (D37 identity) records it, and the version history line names 1.4; `test_packaging.py` expects 1.4.
- **D102 wake bound as a test.** A regression drives the dispatcher with a fake wake transport through: bystander
  read before the ping, owner read, unregistered-Codex read after a restart, repeated reads; it asserts at most one
  successful ping per message and that no job leaves `accepted` / `read` / final back to `pending`.
- **D103 docs.** Bridge README tool table if it describes reads, the collab skill's inbox guidance, `UPSTREAM.md`,
  CHANGELOG `[Unreleased]` (interface 1.4).

## Requirements

0. Red first (bridge, over MCP with two sessions): a bystander's `bridge_inbox` leaves the message `queued` /
   `sending` / `accepted` exactly as before, keeps the pending wake job pending, returns `readRecorded: false` and the
   note; the owner's read records it (`readRecorded: true`); the same for `bridge_wait` with `acknowledge: false`; a
   bystander's `bridge_outbox` does not change the sender's `lastActivity`.
1. Codex restart case: a Codex identity registered in one bridge process, read through a second process without
   registering → `readRecorded: false`; after `bridge_register` in that process → true. A Claude identity read after
   a restart (same verified session) → true.
2. D102 regression.
3. Python: packaging test expects 1.4; `relay_status.py` reports 1.4.
4. Live check per assumption 7; validate on three Pythons; CI green.

## Boundaries

- Always: the sealed state root in tests; manifest and `UPSTREAM.md` with every bridge change.
- Ask first: the real `~/.agent-relay`, `~/.claude`, `~/.codex`; authenticating reads; any schema change; renaming or
  removing an existing field.
- Never: merge before the round-2 coordinator's review; push without approval.

## Success criteria

Only the identity itself moves its messages to read; a bystander's read leaves delivery and pings untouched and says
so; no message is pinged more than once; interface 1.4 is declared and documented.

## Open questions

None. Accepted by the user on 2026-10-08: assumptions 1–7, D99–D103 (including D100's note text).
