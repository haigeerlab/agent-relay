# Todo: paused-session-link

- [x] Task 1: schema 8 and the `desktop` field on `bridge_register` (D287, D288)
  - Accepted by the owner: new `desktop-link.test.ts` and schema tests; title cleanup also strips C1 controls; `request-closing.test.ts` pins schema 8; bridge `npm run check` 338 pass; `bash scripts/validate.sh` pass (51 files, 1082 tests).
- [x] Task 2: hooks read schema 8 (D288)
  - Accepted by the owner: `MAILBOX_SCHEMA_VERSIONS` gains 8, `ROLLBACK_CAVEAT` names schema 8 and read-only CLI commands; retire and doctor tests updated.
- [x] Task 3: one "not running" wording and the manual-wake sentence (D289, D291)
  - Accepted by the owner: new `paused-wording.test.ts`; owner fixes: first parts no longer repeat the cause, the notification body speaks to the user (no "Tell the user"), titles in single quotes; Spec D289 updated to match (to show at the final gate). Bridge `npm run check` 340 pass; `bash scripts/validate.sh` pass (51 files, 1086 tests).
- [ ] Task 4: the offline notification opens the session (D290)
- [ ] Task 5: `bridge_agents` carries `desktop` (D292)
- [ ] Task 6: interface 2.12, skill, docs and bookkeeping (D293)
- [ ] Checkpoint (report): owner acceptance of Tasks 1–6
- [ ] Checkpoint (gate): PR review and merge by the user
