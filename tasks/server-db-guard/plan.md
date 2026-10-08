# Plan: server-db-guard

Based on [`spec/server-db-guard.md`](../../spec/server-db-guard.md) (accepted by the user on 2026-10-08:
assumptions 1–8, D114–D115). Branch `claude/server-db-guard` from main 112d26d. Red → green, one commit per task.
The round-2 coordinator reviews the PR before the user merges. No release in this module.

Code: `bridge/src/server.ts`; tests: new `bridge/test/server-db-guard.test.ts`. After any change under `bridge/`
(tests included) regenerate `UPSTREAM.sha256`. Record validate only after its output says `validate: pass`.

## Task List

### Task 1: the server refuses to start without BRIDGE_DB_PATH (D114)
Red first in `server-db-guard.test.ts` (spawn `src/server.ts` via `tsx`, temporary HOME and `XDG_DATA_HOME`, stdin
closed, a timeout so an unguarded server cannot hang the test): a planted default database with one agent and no
variable → exit 2, stderr `[agent-relay] BRIDGE_DB_PATH is not set` naming `native_collaboration_adapters.py`, bytes,
mtime and directory listing unchanged; no default database, unset and `"  "` → exit 2, nothing created under HOME.
Then `server.ts` `main()`: read and trim the variable, `log` the line, `process.exitCode = 2`, return before
`BridgeStore`; drop the `defaultDbPath` import. Other bridge tests unchanged. `UPSTREAM.md` row, manifest, CHANGELOG.

### Task 2: docs (D115)
Bridge README storage paragraph: the server refuses without `BRIDGE_DB_PATH` and is started only by the host entries.
`UPSTREAM.md` row, manifest.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 3: live check
`mktemp -d` HOME with `AGENT_RELAY_HOME` inside: install a runtime from this branch; plant a default database;
`node runtime/dist/server.js </dev/null` without the variable → exit 2 with the line, planted file unchanged; `probe`
→ ready, 10 tools; `doctor` probe ok. Temporary HOME to the Trash.

### Checkpoint (gate): module review
Then push and PR with the user's approval; the round-2 coordinator reviews; the user merges after CI is green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A launcher that does not pass the variable stops working | High | every launcher listed in the spec passes it (probe and delegation tests stay green); live probe and doctor |
| An unguarded server in the red test waits on stdin forever | Low | stdin closed and a spawn timeout |
