# Spec: retire-cli-guard

## Objective

Since `legacy-cli-cleanup` the bridge's TS CLI (`runtime/dist/cli.js`) has only `retire` and `help`, and its one caller
is `native_collaboration_retire.py`, which always passes `BRIDGE_DB_PATH`. Run by hand without it, `cli.js retire`
falls back to the upstream default database `$XDG_DATA_HOME/claude-codex-bridge/bridge.sqlite` (or
`~/.local/share/claude-codex-bridge/bridge.sqlite`): it opens or creates that file, answers "Unknown agent", and
touches its mtime. Found by the round-2 coordinator during the 0.5.0 real-host re-check (F1, PR #36); on this Mac the
file is an empty database left in September. The user chose (2026-10-08) to make the CLI refuse instead of only
documenting it.

Readers: the user, who might run the CLI by hand; the round-2 coordinator, who reviews the PR before the user merges.

## What exists today (main 52012f0, 2026-10-08)

- `bridge/src/cli.ts:22-38` `retire`: `new BridgeStore(defaultDbPath())`, then `retireAgent`; prints `✓ Retired …`,
  exits 0; any error prints `✗ <message>` and exits 1. A parse error prints the usage and exits 2 (`:45-52`).
- `bridge/src/paths.ts:23-25` `defaultDbPath`: `BRIDGE_DB_PATH` (trimmed, empty means unset) else
  `dataDir()/bridge.sqlite`, where `dataDir` is `$XDG_DATA_HOME` or `~/.local/share` plus `DATA_DIR_NAME`
  (`claude-codex-bridge`, kept on purpose by legacy-cli-cleanup D96).
- `hooks/native_collaboration_retire.py:86-91` runs `node <root>/dist/cli.js retire <name> --keep-backlog [--note …]`
  with `BRIDGE_DB_PATH=<root>/mailbox/bridge.sqlite` and `XDG_DATA_HOME=<root>/data`.
- `bridge/src/server.ts:63` uses the same `defaultDbPath()`; the host entries always set `BRIDGE_DB_PATH`.
- `bridge/test/cli.test.ts` runs the CLI with `BRIDGE_DB_PATH` set; README, INSTRUCTIONS and the collaboration-ops
  skill already name only the Python script for retiring.

## Assumptions (accepted by the user 2026-10-08)

1. Only `cli.js retire` changes: without `BRIDGE_DB_PATH` it refuses. `help` touches no mailbox and works as before.
2. The MCP server's fallback (`server.ts:63`) is out of scope: hosts always pass `BRIDGE_DB_PATH`.
3. The refusal exits 2 (like a usage error; 1 still means the retirement failed), names
   `native_collaboration_retire.py` on stderr, and happens before any database is opened: a missing default database
   is not created, an existing one is not opened (content and mtime unchanged).
4. An empty or blank `BRIDGE_DB_PATH` counts as unset (same as `paths.ts`).
5. A set `BRIDGE_DB_PATH` is used as given; the CLI does not check that it is the runtime's mailbox.
6. `native_collaboration_retire.py` already passes the variable; its behaviour, output and exit codes are unchanged.
7. The interface stays 1.4 (the CLI is not part of `interface.json`; Spec Guard does not call it). No release in this
   module; the change reaches the real host with the next runtime upgrade.
8. Tests first in `bridge/test/cli.test.ts`; regenerate `UPSTREAM.sha256`, add an `UPSTREAM.md` row and a CHANGELOG
   `[Unreleased]` entry; bridge README and the collaboration-ops skill say to retire only through the Python script;
   validate on Python 3.9, 3.10, 3.14; the round-2 coordinator reviews the PR before the user merges.

## Decisions

- **D111 explicit mailbox.** `cli.ts` `retire` reads `BRIDGE_DB_PATH` itself (trimmed; empty is unset). When it is
  unset it prints to stderr `retire needs BRIDGE_DB_PATH (the agent-relay mailbox); retire an identity with
  native_collaboration_retire.py --name <agent> --confirm-retire` and exits 2, before constructing `BridgeStore`. When
  it is set, `retire` opens exactly that path, as today. `defaultDbPath` and `paths.ts` are unchanged.
- **D112 help.** `USAGE` gains one line under `retire` saying it needs `BRIDGE_DB_PATH` and is run by
  `native_collaboration_retire.py`; `help` still needs nothing.
- **D113 docs.** Bridge README (retire section) and the collaboration-ops skill add one sentence: do not run
  `dist/cli.js` directly; it refuses without `BRIDGE_DB_PATH`. `UPSTREAM.md` row for `src/cli.ts` and
  `test/cli.test.ts`; CHANGELOG `[Unreleased]`.

## Requirements

0. Red first (`cli.test.ts`, temporary HOME and `XDG_DATA_HOME`):
   - with an existing default database (a real SQLite file with one agent) and no `BRIDGE_DB_PATH`: `retire <name>`
     exits 2, stderr names `native_collaboration_retire.py`, the file's bytes and mtime are unchanged, the agent is not
     retired;
   - with no default database and no `BRIDGE_DB_PATH` (also with `BRIDGE_DB_PATH="  "`): exits 2 and no file or
     directory is created under the data home;
   - `help` without `BRIDGE_DB_PATH` exits 0 and mentions the requirement.
1. The existing CLI tests (retire with `BRIDGE_DB_PATH`, output, exit codes, `--keep-backlog`) and
   `test_native_collaboration_retire.py` stay green unchanged.
2. Validate on three Pythons; bridge `npm run check`; CI green.
3. Live check in a temporary HOME: a runtime from this branch; `node dist/cli.js retire x` without the variable →
   exit 2, the planted default database unchanged; `native_collaboration_retire.py --name … --confirm-retire` → retired.

## Boundaries

- Always: temporary HOME and data home in tests; regenerate `UPSTREAM.sha256` after any bridge change; record validate
  only after its output says `validate: pass`.
- Ask first: the real `~/.agent-relay` and `~/.local/share/claude-codex-bridge` (leave the September database alone).
- Never: change `defaultDbPath`, `DATA_DIR_NAME` or the server's database choice; merge before the round-2
  coordinator's review.

## Success criteria

`node dist/cli.js retire <name>` without `BRIDGE_DB_PATH` never opens or creates a database and points to the Python
script; retiring through `native_collaboration_retire.py` behaves exactly as before.

## Open questions

None. Accepted by the user on 2026-10-08 ("接受"): assumptions 1–8, D111–D113.
