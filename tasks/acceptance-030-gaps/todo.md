# Todo: acceptance-030-gaps

- [x] Task 1: Warn when the recipient has no wake binding and no known host (D72) — new `notify.test.ts` test (Codex caller registers `cx2` with `wake: null`; duplicate, `wake: false`, broadcast and a recorded Claude host stay silent; no notice logged): red with no `warnings` in the send result, green after `server.ts` adds the warning under `!duplicate && wake !== false && recipient && !recipient.host && !wakes.target(to)`. The full suite then showed `mcp-integration.test.ts` "two independent MCP clients" asserting no warnings for exactly this case (`codex` registered without wake from a Codex client); its expectation now names the D72 warning. Bridge `npm test` 149/149. `UPSTREAM.md` row, `UPSTREAM.sha256` regenerated (75 files), CHANGELOG entry
- [ ] Task 2: Same-second upgrade picks a suffixed stamp (D74)
- [ ] Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`
- [ ] Task 3: Live check in a temporary AGENT_RELAY_HOME/HOME, then the README paragraph (D73)
- [ ] Checkpoint (gate): module review
