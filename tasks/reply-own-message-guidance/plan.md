# Plan: reply-own-message-guidance

Based on [`spec/reply-own-message-guidance.md`](../../spec/reply-own-message-guidance.md) (accepted by the user on
2026-10-16, D211, option (b)). Built second in `claude/relay-071-impl` (see the plan of `codex-identity-recovery`);
bridge commits carry the manifest and `UPSTREAM.md` row (D24).

## Task List

### Task 1: the refusal names a way forward (D211)
Red first (requirements 1–2), `bridge/test/idempotency.test.ts`: `replyTo` at the caller's own direct message on
thread T is refused with the recipient, `threadId "T"` and "without replyTo"; on a message without thread the text says
to send a new message citing #N and has no `threadId`; the caller's own broadcast gets the same guidance with
recipient `*`; a third party keeps the current refusal; the recipient's reply still works; a `threadId` other than the
original's names the original's thread or "has no thread" and says to omit `threadId`. In
`awaiting-reply.test.ts`: following the guidance (new message on T without `replyTo`) leaves the original request in
`awaitingReply`.
Green: `idempotency.ts` `assertMayReply` takes the original's thread and branches on `sender === originalFrom`;
`replyThread` wording; the caller in `bridge-store.ts` passes the thread.
Files: `src/idempotency.ts`, `src/bridge-store.ts`, `test/idempotency.test.ts`, `test/awaiting-reply.test.ts`.

### Task 2: skills
`skills/collab` and `skills/session-routing`: to add to one's own message, send a new message on its thread (or citing
#N when it has none), never `replyTo` to oneself.
Files: two `SKILL.md`.

### Checkpoint (report): bridge green
`npm run check`.

### Checkpoint (report): module done
Todo checked; `activeModule` → `read-own-sent`.
