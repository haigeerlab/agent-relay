# Todo: agents-view-polish

- [x] Task 1: `bridge_agents` pages; retired entries compact (D223) — red first through the MCP server (no `hasMore`, no paging), then paging only with `includeRetired`, `maxChars` or `afterName`, a `textCost` budget with at least one entry, `afterName` continuing in registration order (unknown refused), compact retired entries; a plain call with 60 agents past 48 000 units stays whole
- [x] Task 2: message status open to every caller (D224) — red first (a third session was refused), then `statusFor` without the party check (also `bridge_wait` by id); the upstream status test now expects the third session to be answered; `bridge_wait` as someone else's name is still refused by the identity check
- [x] Task 3: Claude presence `activity` (D225) — red first in `presence.test.ts`, then `activity` for registry `busy`/`idle` on `running` only
- [x] Task 4: the 2 s cap (D226) — red first: `bridge_agents` took 10 008 ms against a silent ChatGPT socket in a temporary HOME; after the cap both calls return within 3 s with `not-loaded`; with only `bridge_send`'s two lookups reverted, it took 10 061 ms (red for the right reason)
- [x] Checkpoint (report): bridge green — `npm run typecheck` clean, `npm test` 256 pass
- [x] Task 5: interface 2.4 and bookkeeping (D227) — `interface.json` 2.4, `test_packaging`, `relay_status.py`, `docs/collaboration-interface.md` (version line, `bridge_agents` incl. `activity` and the 2 s `not-loaded` note, `bridge_wake_status`), `UPSTREAM.md` row, manifest regenerated after the last bridge edit, `bridge/CHANGELOG.md` 0.8.1, CHANGELOG `[Unreleased]`
- [ ] Checkpoint (report): local validation
- [ ] Task 6: PR and CI
- [ ] Checkpoint (gate): module review
