# Todo: reply-own-message-guidance

- [x] Task 1: the refusal names a way forward (D211) — red first in `idempotency.test.ts` (own direct with thread → `threadId "t1"` and without replyTo; without thread → "Addendum to #N:" and no `threadId`; own broadcast → recipient `*`; third party keeps the recipient-only refusal; recipient still replies; the guidance works) and `awaiting-reply.test.ts` (the addendum leaves the request open); then `assertMayReply` takes the original's thread, `addendum()` words the way forward; the thread-mismatch refusal already named the thread and "omit threadId" (existing test)
- [x] Task 2: skills — `collab` and `session-routing`: add to one's own message with a new message on its thread, or "Addendum to #N:" when it has none, never self-`replyTo`
- [x] Checkpoint (report): bridge green — `npm run typecheck` clean, `npm test` 224 pass
- [x] Checkpoint (report): module done — `activeModule` → `read-own-sent`
