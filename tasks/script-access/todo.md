# Todo: script-access

- [x] Task 1: read-only store (D242) — red first (3 cases), then green
- [x] Task 2: shared views in `src/views.ts`; MCP output unchanged (D241) — red first (module missing); the comparison takes `bridge_agents` after `bridge_outbox`, which records the owner's `lastSeen`
- [x] Task 3: script identity (D244) — tests written first; `bridge_register` on a script identity's name says so and needs `takeover`
- [x] Task 4: CLI `agents`, `outbox`, `sessions`, `send`, `register-script-identity` (D241–D244) — red first (5 cases), then green; `bridge_send`'s core moved to `src/send.ts` for both; `send` waits up to 5 s for a late Claude receipt; one flush like `bridge_send` (the next due ping, in per-recipient order); a race test with a running dispatcher pings once
- [x] Checkpoint (report): bridge green — `npm run check` 294 tests ok
- [x] Task 5: launcher, doctor `script-launcher`, rollback, uninstall (D240) — red first (7 cases, import missing), then green; `write_launcher` never raises, it reports `{path, ok, node, diagnostic}` in the install, upgrade and rollback results and runs `--version` under `PATH=/usr/bin:/bin`; rollback keeps the node the old launcher named; doctor's fixture and the reinstall test now expect the launcher
- [x] Task 6: interface 2.8 and docs (D245) — `interface.json` `script` block, interface document §2.4, README zh/en "脚本与 launchd", `collaboration-ops`, both CHANGELOGs, `UPSTREAM.md`, manifest
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10, 3.14 with Node v24.18.0 first on PATH (48 files, 905 tests each; bridge `npm run check` 294 ok)
- [x] Task 7: PR and CI — #149 (feature) and #151 (post-merge review fixes) merged; released as 0.9.0 (#150), tag v0.9.0 = efaae59
- [x] Checkpoint (gate): module review — the user merged #149 (57ed0a3) on 2026-10-19 before the round-2 coordinator's review came back; it became a post-merge review (#9192); released as 0.9.0 at the user's request

## Rework after the round-2 post-merge review (#9193, 2026-10-19; the user asked for it the same day)

0.9.0 is on main (#150) but not tagged yet; these fixes go into the 0.9.0 CHANGELOG section and the tag follows them.

- [x] Task 8: the launcher keeps node's path as found (`Path.absolute()`, no symlink resolution), so a Homebrew upgrade that replaces the versioned Cellar directory does not break it — red first with a symlinked node (4 new cases failed, then green)
- [x] Task 9: install, upgrade and rollback say on stderr when the launcher was not written or did not run; the temporary file name is unique per process; the rollback test covers the node recorded in the old launcher and `launcher.ok`
- [x] Task 10: the CLI's late-receipt wait reads the Claude adapter's exported detail constant instead of matching its text; a test covers a session that never sends a receipt (one ping, state `unknown`) — red first, then green
- [x] Task 11: docs — a 0.8.x bridge warns "Codex task is not open" when a session sends to a script identity (spec D244, CHANGELOG); `send`'s one flush may dispatch another message's ping first, as `bridge_send` does (interface §2.4)
- [x] Checkpoint (report): local validation and PR — `scripts/validate.sh` pass on Python 3.9.6 + Node 22.22.0, 3.10 + Node 24.18.0, 3.14 + Node 22.22.0 (48 files, 910 tests each); `test_node_everywhere` now parses the JSON line and expects the launcher warning its fake node causes
