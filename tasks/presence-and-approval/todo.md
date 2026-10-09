# Todo: presence-and-approval

- [x] Task 1: presence reading and the directory (D146) — new `test/presence.test.ts` (4: the mapping table — idle/busy/unknown status running, `waiting` + permission prompt waiting-approval with `since` from `statusUpdatedAt`, other waiting waiting-input, no matching live session stopped, unreadable registry unknown; on macOS a real registry fixture with a listening socket keeps `status`, `statusUpdatedAt`, `waitingFor` and drops wrongly typed ones; a fake Codex IPC says running with an owner, stopped without, unknown without the socket; `bridge_agents` gives every agent a `presence`, a Claude agent with no registry file is stopped): red on typecheck (no `presence.ts`, no status fields). Then `claude-wake.ts` keeps the three fields, new `presence.ts` (`claudePresence`, `codexOwner`, `codexPresence`), `bridge_agents` reads the registry once per listing and asks Codex per Codex agent. 4 green; `UPSTREAM.md` row and manifest in the same commit
- [ ] Task 2: the sender is told (D147)
- [ ] Task 3: the approval notice (D148)
- [ ] Task 4: doctor shares the reading (D149)
- [ ] Task 5: skill, README, CHANGELOG, bridge records
- [ ] Checkpoint (report): local validation
- [ ] Task 6: PR and CI
- [ ] Checkpoint (gate): module review
