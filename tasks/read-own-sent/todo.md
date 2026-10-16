# Todo: read-own-sent

- [ ] Task 1: read one's own sent message by id (D212) — red first (own direct and broadcast, `bodyOffset`, `direction`, no read recorded for anyone, expired), then `messagePart` and `server.ts`
- [ ] Task 2: the refusal says why and whom to ask (D213) — third party named sender/recipient with the agreed wording; nonexistent id
- [ ] Checkpoint (report): bridge green — `npm run check`
- [ ] Task 3: interface 2.2 and docs (D214) — interface doc, `interface.json`, version tests, `collab`
- [ ] Task 4: bridge docs and bookkeeping for 0.7.1 — bridge CHANGELOG, INSTRUCTIONS if needed, CHANGELOG `[Unreleased]`, READMEs where behaviour changed
- [ ] Checkpoint (report): local validation — `scripts/validate.sh` on Python 3.9, 3.10, 3.14 with Node 24
- [ ] Checkpoint (gate): module review — implementation PR reviewed by the coordinator and merged by the user; then the 0.7.1 release PR
