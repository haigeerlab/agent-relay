# Todo: read-own-sent

- [x] Task 1: read one's own sent message by id (D212) — red first in the new `read-own-sent.test.ts` (own direct in parts and own broadcast with `direction: "sent"`, the recipient's read `"received"`, no `read_at`, ping not read, still unread for the recipient; `readRecorded: false` with a note, from the round-2 review of #122/#123; an expired own message is still readable history, review item 4 settled as "readable"), then `messagePart` and `server.ts`
- [x] Task 2: the refusal says why and whom to ask (D213) — third party: the user's wording, sender and recipient named, no hint to read another inbox; nonexistent id: "There is no message #N"; the `long-messages` assertion follows the new wording
- [x] Checkpoint (report): bridge green — `npm run typecheck` clean, `npm test` 227 pass
- [x] Task 3: interface 2.2 and docs (D214) — `interface.json` 2.2, `test_packaging`, `relay_status.py` docstring, `docs/collaboration-interface.md` (version line, `bridge_inbox` row), `collab`
- [x] Task 4: bridge docs and bookkeeping for 0.7.1 — `bridge/CHANGELOG.md` 0.7.1 section, CHANGELOG `[Unreleased]`, `UPSTREAM.md` rows and manifest; `bridge/INSTRUCTIONS.md` needed no reading-by-id change; the README interface lines move to 2.2 in the release PR with the status lines
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH (47 files, 830 tests each; bridge `npm run check` 227 ok)
- [ ] Checkpoint (gate): module review — implementation PR reviewed by the coordinator and merged by the user; then the 0.7.1 release PR
