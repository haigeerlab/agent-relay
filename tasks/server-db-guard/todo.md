# Todo: server-db-guard

- [x] Task 1: the server refuses to start without BRIDGE_DB_PATH (D114) — new `server-db-guard.test.ts` (spawn `src/server.ts` via `tsx`, temporary HOME and `XDG_DATA_HOME`, stdin closed, 20 s timeout): a planted default database with one agent (mtime 2026-09-01) and no variable → exits on its own with 2, stderr `[agent-relay] BRIDGE_DB_PATH is not set` naming `native_collaboration_adapters.py install-claude / install-codex`, stdout empty, bytes, mtime and directory listing unchanged; unset and `"  "` with no default database → exit 2, nothing created under HOME. Red 2/2 (the old server logged `store ready at …/claude-codex-bridge/bridge.sqlite`, created or opened it, and exited 0 on stdin EOF), green after `server.ts` `main()`: read and trim the variable, `log` the line, `process.exitCode = 2`, return before `BridgeStore`; `defaultDbPath` import dropped. No other test changed. `UPSTREAM.md` row, manifest, CHANGELOG. `scripts/validate.sh` pass on Python 3.10.7 (output checked): 39 files, 600 tests, bridge 153
- [ ] Task 2: docs (D115)
- [ ] Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`
- [ ] Task 3: live check
- [ ] Checkpoint (gate): module review
