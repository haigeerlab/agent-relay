# Todo: codex-identity-recovery

- [x] Task 1: the refusal for an unverified Codex caller (D209) — red first in `identity.test.ts` (restart, refusal with the exact `bridge_register` call and "no takeover", re-register with `host` keeps the wake binding, the refused send then passes; a verified caller keeps the takeover sentence), then `identity.ts` `require()`; the `host-claim` assertion now matches the new wording (still refused)
- [x] Task 2: skills and instructions (D209, D210) — `collab` (re-register and repeat, no rename, no takeover; rename only when registration itself is refused; `Transport closed` stops and hands the restart to the user), `session-routing` pointer beside the mailbox send rules, `bridge/INSTRUCTIONS.md`, server instructions sentence asserted through `getInstructions()` in `awaiting-reply.test.ts`
- [x] Checkpoint (report): bridge green — `npm run typecheck` clean, `npm test` 222 pass (Node v24)
- [x] Checkpoint (report): module done — `activeModule` → `reply-own-message-guidance`
