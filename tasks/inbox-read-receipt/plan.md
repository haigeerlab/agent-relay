# Plan: inbox-read-receipt

Based on [`spec/inbox-read-receipt.md`](../../spec/inbox-read-receipt.md) (accepted by the user on 2026-10-08:
assumptions 1–7, D99–D103). Branch `claude/inbox-read-receipt` from main 5c557eb. Red → green, one commit per task.
Third module of 0.5.0; no release at its end. After the PR opens, the round-2 coordinator reviews before the user
merges.

## Task List

### Task 1: only the identity itself records a read (D99, D100)
Red first, over MCP with two Claude-style sessions on one mailbox (`test/support/session.ts`): a bystander's
`bridge_inbox` leaves the message's `deliveryState` and its pending wake job unchanged and returns
`readRecorded: false` with the D100 note; the owner's read records it (`readRecorded: true`, message `accepted`); the
same pair for `bridge_wait` with `acknowledge: false`; `readRecorded: true` on an empty owner page; a bystander's
`bridge_outbox` leaves the sender's `lastActivity` unchanged. Then `server.ts` (the three handlers, the two
descriptions).
Files: `src/server.ts`, a new `test/read-receipt.test.ts`; `UPSTREAM.md`, manifest, CHANGELOG.

### Task 2: restart cases and the wake bound (D102)
Tests first: a Codex identity registered through one bridge process and read through a second without registering →
`readRecorded: false`, then `true` after `bridge_register` there; a Claude identity read after a restart (same
verified session) → `true`. The D102 regression with the dispatcher and a fake wake transport: bystander read before
the ping, owner read, unregistered-Codex read, repeated reads → at most one successful ping per message, no job back
to `pending`. Expected green without code changes (the bound comes from `claimStep`); any red is a stop-and-ask.
Files: `test/read-receipt.test.ts`.

### Checkpoint (report): bridge check, validate on one Python

### Task 3: interface 1.4 and docs (D101, D103)
Red first: `test_packaging.py` expects `1.4`. Then `interface.json`; `docs/collaboration-interface.md` (§2.1
`bridge_inbox` / `bridge_wait` rows, "Message read" row, version line 178); collab skill inbox guidance; bridge README
if it describes reads; CHANGELOG `[Unreleased]` (interface 1.4).

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 4: live check with two clients
Runtime from this branch in a `mktemp -d` HOME (`install`, no hosts needed): over stdio MCP, an owner session and a
bystander session; a message to the owner while it is unbound or bound to a fake target; bystander `bridge_inbox` →
`readRecorded: false`, `bridge_wake_status` / outbox show the message still `queued` or `accepted` as before; owner
`bridge_inbox` → `readRecorded: true`, message `accepted`, wake job `read`. `relay_status.py` reports interface 1.4.
Temporary HOME to the Trash.

### Checkpoint (gate): module review
Then push and PR with the user's approval; tell the round-2 coordinator and wait for its review; the user merges after
CI is green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| An owner's read stops being recorded (wrong identity check), so pings repeat | High | Task 1 owner cases; Task 2 restart cases and the D102 bound |
| Codex sessions after a bridge restart see `readRecorded: false` for their own reads | Medium (accepted, D100 note) | Note tells them to register again; bound of one extra ping (assumption 5) |
| Spec Guard reads the interface version wrongly | Low | Range `>=1.0,<2.0` unchanged; the coordinator confirms |
