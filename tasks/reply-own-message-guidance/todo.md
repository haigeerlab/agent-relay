# Todo: reply-own-message-guidance

- [ ] Task 1: the refusal names a way forward (D211) — red first in `idempotency.test.ts` (own direct with and without thread, own broadcast, third party, recipient, thread mismatch) and `awaiting-reply.test.ts` (the request stays open), then `assertMayReply` / `replyThread`
- [ ] Task 2: skills — `collab` and `session-routing`: add to one's own message on its thread or citing #N, never self-`replyTo`
- [ ] Checkpoint (report): bridge green — `npm run check`
- [ ] Checkpoint (report): module done — `activeModule` → `read-own-sent`
