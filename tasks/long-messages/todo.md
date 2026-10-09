# Todo: long-messages

- [x] Task 1: the send result carries no body (D150) — new `test/long-messages.test.ts`: a 160 000-byte Chinese `bodyFile`, sent twice with one idempotency key, returns no `body`, `bodyLength` equal to the body's length and a result under 2 000 characters both times: red (the body came back), green after `bridge_send` drops `body` and adds `bodyLength`. `mcp-integration.test.ts` pinned the echoed body; now checks `bodyLength`. Bridge `npm run check` 161 green
- [ ] Task 2: budgets in token-safe units (D151)
- [ ] Task 3: read a long body in parts, and say how (D152, D153)
- [ ] Task 4: skill, tool descriptions, README, CHANGELOG
- [ ] Checkpoint (report): local validation
- [ ] Task 5: PR and CI
- [ ] Checkpoint (gate): module review
