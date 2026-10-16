# Todo: awaiting-reply-view

- [x] Task 1: schema 6 and the marked send — red first (5 cases in the new `test/awaiting-reply.test.ts`), then `SCHEMA_VERSION = 6` with `messages.expects_reply`, `expectsReply` on `SendInput`/`BridgeMessage`/`bridge_send`, broadcast refusal, `contentDifferences` includes it; the v2 migration test now migrates to 6
- [x] Task 2: the asking view (`bridge_outbox` `awaitingReply`) — `OPEN_REQUEST` (D202), `outbox` `awaitingReply` oldest first with `waitingSeconds` and `totalAwaitingReply`, `expectsReply` on every entry; `src/awaiting-reply.ts` `pagePresence` (distinct page recipients, none for retired) and `awaitingCodexPresence` (2 s, silence → `unknown` with the D200 wording); counting fake, silent-socket timing and an MCP end-to-end test
- [x] Task 3: the asked view (`bridge_agents` `owesReplies`) — `BridgeStore.owesReplies()` `{count, ids (oldest 20), oldestAt}`, shown on `bridge_agents`; reply, expiry and retirement remove it
- [x] Checkpoint (report): bridge green — `npm run check` 221 tests pass (Node v24.18.0); each bridge commit carries its manifest and `UPSTREAM.md` row
- [x] Task 4: Python hooks (schema 6, D208) — red first (backend, retire, doctor tests), then `MAILBOX_SCHEMA_VERSIONS = (2, 3, 4, 5, 6)`, `newer_mailbox_schema()` ("update the agent-relay plugin on both hosts"), `retire` raises it instead of a bare "unavailable", `resolve_backend` stops with `mailbox-schema-newer` (detail in `REASON_DETAILS`) rather than probes reading None, `ROLLBACK_CAVEAT` names schema 6; validate 824 tests pass
- [ ] Task 5: skills, server instructions, interface
- [ ] Task 6: bridge documents and bookkeeping
- [ ] Checkpoint (report): local validation
- [ ] Checkpoint (gate): module review
