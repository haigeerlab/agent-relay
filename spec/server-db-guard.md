# Spec: server-db-guard

## Objective

`retire-cli-guard` (D111) stopped `dist/cli.js retire` from falling back to the upstream default database. The MCP
server has the same fallback: started without `BRIDGE_DB_PATH`, `dist/server.js` opens (or creates)
`$XDG_DATA_HOME/claude-codex-bridge/bridge.sqlite` (or `~/.local/share/claude-codex-bridge/bridge.sqlite`) and serves a
second, private mailbox that no other session sees. Every launcher agent-relay owns passes the variable, so this only
happens on a manual start, but such a server would accept registrations and sends that silently go nowhere. Found
while reviewing #37; the user chose (2026-10-08) to close it as its own module.

Readers: the user; the round-2 coordinator, who reviews the PR before the user merges.

## What exists today (main 112d26d, 2026-10-08)

- `bridge/src/server.ts:62-64` `main`: `const dbPath = defaultDbPath(); const store = new BridgeStore(dbPath);` before
  the identity, wake dispatcher, housekeeper and stdio transport; `log()` (`:28-30`) writes `[agent-relay] <message>` to
  stderr; a failed `connect` logs `fatal: …` and exits 1 (`:539-543`).
- `bridge/src/paths.ts:23-25` `defaultDbPath`: `BRIDGE_DB_PATH` (trimmed, blank = unset) else
  `dataDir()/bridge.sqlite`; after this module only tests call it.
- Launchers that pass `BRIDGE_DB_PATH`: host entries (`hooks/native_collaboration_adapters.py:52`, `:64`), the runtime
  probe (`hooks/native_collaboration_runtime.py:308`), Codex delegation (`hooks/session_delegation_codex.py:47`, it
  refuses without it), bridge tests (`test/mcp-integration.test.ts:24`, `test/idempotency.test.ts:103`). doctor checks
  that the host entries carry it (`hooks/native_collaboration_doctor.py:175`, `:187`).
- Bridge README `:151` says the host entries pass `BRIDGE_DB_PATH`.

## Assumptions (accepted by the user 2026-10-08)

1. Only `server.ts` `main()` changes: it reads `BRIDGE_DB_PATH` itself (trimmed, blank = unset) and refuses before
   constructing `BridgeStore`. `defaultDbPath` in `paths.ts` is unchanged (the CLI tests use it to locate the default
   database).
2. Host entries, the probe and Codex delegation already pass the variable; their behaviour is unchanged. Only a manual
   `node server.js` without it is refused.
3. The refusal writes one `[agent-relay]` line to stderr saying `BRIDGE_DB_PATH` is missing and that the server is
   started by the host entries `native_collaboration_adapters.py install-claude / install-codex` attach, then exits 2
   (as the CLI). It happens before any database is opened and before the stdio transport starts, so a default database
   is neither created, opened nor changed; the host shows the MCP server failing to start with that line.
4. A set `BRIDGE_DB_PATH` is used as given; the server does not check that it is the runtime's mailbox.
5. The interface stays 1.4 (the server's environment is not part of `interface.json`; Spec Guard reads only that
   file). No release in this module; it ships with `retire-cli-guard` in the next version.
6. Red first, in a temporary HOME and data home: a planted default database and no variable → exit 2, the line on
   stderr, bytes and mtime unchanged; no default database and the variable unset or blank → exit 2, nothing created
   under HOME; the existing server tests (started with the variable) stay green.
7. Regenerate `UPSTREAM.sha256`, `UPSTREAM.md` row, CHANGELOG `[Unreleased]`; bridge README says the server is only
   started by the host entries. Validate on Python 3.9, 3.10, 3.14. Live check in a temporary HOME: a manual start is
   refused; with the runtime installed, probe and doctor still show 10 tools.
8. The round-2 coordinator reviews the PR before the user merges.

## Decisions

- **D114 explicit mailbox for the server.** `main()` starts with `const dbPath = process.env.BRIDGE_DB_PATH?.trim();`;
  when it is empty it calls `log("BRIDGE_DB_PATH is not set: the agent-relay mailbox server is started by the host
  entries that native_collaboration_adapters.py install-claude / install-codex attach")` and sets
  `process.exitCode = 2`, returning before `BridgeStore`, the dispatcher, the housekeeper and the transport exist. The
  `defaultDbPath` import leaves `server.ts`.
- **D115 docs.** Bridge README (storage paragraph) says the server refuses to start without `BRIDGE_DB_PATH` and is
  started only by the host entries; `UPSTREAM.md` rows for `src/server.ts`, the new test and `README.md`; CHANGELOG
  `[Unreleased]`.

## Requirements

0. Red first (new `bridge/test/server-db-guard.test.ts`, spawning `src/server.ts` through `tsx` with a temporary HOME
   and `XDG_DATA_HOME`, stdin closed):
   - a planted default database (a real SQLite file with one agent, mtime set back) and no `BRIDGE_DB_PATH`: exit 2,
     stderr has `[agent-relay] BRIDGE_DB_PATH is not set` and names `native_collaboration_adapters.py`, the file's
     bytes, mtime and directory listing unchanged;
   - no default database, the variable unset and `"  "`: exit 2, nothing created under HOME.
1. `mcp-integration`, `idempotency`, `read-receipt` and every other bridge test stay green unchanged; the runtime
   probe and doctor tests stay green.
2. Validate on three Pythons; bridge `npm run check`; CI green.
3. Live check in a temporary HOME: `node runtime/dist/server.js </dev/null` without the variable → exit 2 with the
   line, a planted default database unchanged; `native_collaboration_runtime.py probe` → ready, 10 tools; `doctor`
   probe ok.

## Boundaries

- Always: temporary HOME and data home in tests; regenerate `UPSTREAM.sha256` after any bridge change; record validate
  only after its output says `validate: pass`.
- Ask first: the real `~/.agent-relay` and `~/.local/share/claude-codex-bridge`.
- Never: change `defaultDbPath`, `DATA_DIR_NAME`, the host entries or the probe's environment; merge before the
  round-2 coordinator's review.

## Success criteria

`dist/server.js` started without `BRIDGE_DB_PATH` never opens or creates a database and says how it should be
started; every agent-relay launcher starts it exactly as before.

## Open questions

None. Accepted by the user on 2026-10-08 ("接受"): assumptions 1–8, D114–D115.
