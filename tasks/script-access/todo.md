# Todo: script-access

- [x] Task 1: read-only store (D242) — red first (3 cases), then green
- [x] Task 2: shared views in `src/views.ts`; MCP output unchanged (D241) — red first (module missing); the comparison takes `bridge_agents` after `bridge_outbox`, which records the owner's `lastSeen`
- [x] Task 3: script identity (D244) — tests written first; `bridge_register` on a script identity's name says so and needs `takeover`
- [x] Task 4: CLI `agents`, `outbox`, `sessions`, `send`, `register-script-identity` (D241–D244) — red first (5 cases), then green; `bridge_send`'s core moved to `src/send.ts` for both; `send` waits up to 5 s for a late Claude receipt; one flush like `bridge_send` (the next due ping, in per-recipient order); a race test with a running dispatcher pings once
- [x] Checkpoint (report): bridge green — `npm run check` 294 tests ok
- [x] Task 5: launcher, doctor `script-launcher`, rollback, uninstall (D240) — red first (7 cases, import missing), then green; `write_launcher` never raises, it reports `{path, ok, node, diagnostic}` in the install, upgrade and rollback results and runs `--version` under `PATH=/usr/bin:/bin`; rollback keeps the node the old launcher named; doctor's fixture and the reinstall test now expect the launcher
- [x] Task 6: interface 2.8 and docs (D245) — `interface.json` `script` block, interface document §2.4, README zh/en "脚本与 launchd", `collaboration-ops`, both CHANGELOGs, `UPSTREAM.md`, manifest
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10, 3.14 with Node v24.18.0 first on PATH (48 files, 905 tests each; bridge `npm run check` 294 ok)
- [ ] Task 7: PR and CI
- [x] Checkpoint (gate): module review — the user merged #149 (57ed0a3) on 2026-10-19 before the round-2 coordinator's review came back; it became a post-merge review (#9192); released as 0.9.0 at the user's request
