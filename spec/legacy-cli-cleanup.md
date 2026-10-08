# Spec: legacy-cli-cleanup

## Objective

The vendored bridge still carries upstream's TypeScript CLI (`claude-codex-mcp-bridge`): setup, doctor, status, demo,
retire, prune, backup, rollback, uninstall. agent-relay installs, upgrades, checks and uninstalls through its Python
runtime and adapters instead, so the TS CLI is a second control plane with its own names (`claude-codex-bridge`), its
own data layout (`~/.local/share/claude-codex-bridge/runtime`) and its own host registration (0.4.0 architecture review,
finding A2). The user decided (2026-10-08) to remove its install control plane and to name what users can see
`agent-relay`. Second module of 0.5.0, after `orchestrator-removal`.

After this module the TS CLI has only `retire` and `help`; installing, upgrading, checking and uninstalling exist only
in Python; the server introduces itself as `agent-relay`.

Readers: the user; the round-2 coordinator, who re-checks on the real host when 0.5.0 is released.

## What exists today (main 931ce63, 2026-10-08)

- Nobody but agent-relay's own retire script runs the TS CLI: the runtime is installed with
  `npm ci --ignore-scripts` (`native_collaboration_runtime.py:239`), which links no `bin`, so `claude-codex-mcp-bridge`
  is not on a user's `PATH`. The only caller is `native_collaboration_retire.py:86`
  (`node <root>/dist/cli.js retire <name> --keep-backlog`).
- `bridge/src/cli.ts` (702 lines) implements every command; `cli-logic.ts` holds `MCP_NAME = "claude-codex-bridge"`,
  `PACKAGE_NAME = "claude-codex-mcp-bridge"`, the parser and setup helpers; only the CLI uses `runtime.ts`,
  `codex-config.ts` and `diagnostics.ts`; `lifecycle.ts` `findStaleAgents` serves only `prune`.
  `scripts/mailbox-request.ts` (an upstream dev tool) imports `runtime.ts` and upstream's runtime layout.
- Names: `server.ts:29` logs as `[claude-codex-bridge]`, `server.ts:112` answers `initialize` with
  `name: "claude-codex-bridge"`; `package.json` / `package-lock.json` name `claude-codex-mcp-bridge` with two `bin`
  entries; `local-ipc.ts:38` sends `clientType: "claude-codex-bridge"` to the Claude/Codex app interface;
  `fs-safety.ts:4` `DATA_DIR_NAME = "claude-codex-bridge"` names the default data directory, used only when
  `BRIDGE_DB_PATH` is unset (agent-relay always sets it, `native_collaboration_adapters.py:53,64`).
- Python `native_collaboration_runtime.py:529` gives doctor a `--claude-settings` option; since `orchestrator-removal`
  doctor no longer reads that file. The adapters' own `--claude-settings` is still used by uninstall.
- `native_collaboration_retire.py:5` still says agents cannot call `bridge_retire` "(it is denied)" — it was removed
  from the server in `orchestrator-removal` (found by the round-2 coordinator).

## Assumptions

1. Deleted CLI commands: setup, uninstall, rollback (they duplicate the Python runtime), and with the user's choice
   also doctor, status, demo, prune, backup: the TS CLI keeps only `retire` and `help`. Python `status` / `doctor` are
   the only status and health checks.
2. Renamed, user-visible only: the server's `initialize` name and log prefix become `agent-relay`; the npm package
   becomes `agent-relay-bridge` (package and lock root), with one `bin` for the CLI; CLI help says `agent-relay-bridge`.
3. Not renamed: `local-ipc.ts` `clientType` (part of the app interface; a change risks the wake path) and
   `DATA_DIR_NAME` (only the default path when `BRIDGE_DB_PATH` is unset; renaming would need a data move for no
   agent-relay user).
4. Python doctor drops `--claude-settings`; the adapters keep theirs.
5. `native_collaboration_retire.py:5` says `bridge_retire` was removed from the server.
6. Interface stays 1.3: the TS CLI is not part of the interface document's public surface.
7. `UPSTREAM.md` and manifest updated; tests red first; validate on Python 3.9, 3.10, 3.14; a live upgrade from
   v0.4.0 in a temporary HOME with `retire` working and doctor all ok.

## Decisions

- **D95 CLI surface.** `cli.ts` parses `retire <agent> [--note TEXT] [--keep-backlog]` and `help`; anything else exits
  2 with the usage text. `retire` behaves exactly as today (same output, same exit codes). Removed with the commands:
  `runtime.ts`, `codex-config.ts`, `diagnostics.ts`, `lifecycle.ts` `findStaleAgents`, the setup/runtime helpers and
  constants in `cli-logic.ts`, `scripts/mailbox-request.ts`, and the CLI tests that covered them.
- **D96 names.** `server.ts` `initialize` name and log prefix `agent-relay`; `package.json` name `agent-relay-bridge`,
  `bin: {"agent-relay-bridge": "dist/cli.js"}` (the server is started by path, `dist/server.js`, never through `bin`);
  `package-lock.json` root name follows (no dependency change). `clientType` and `DATA_DIR_NAME` unchanged (assumption
  3).
- **D97 Python.** Runtime doctor without `--claude-settings` (the `doctor()` parameter goes too); the retire script's
  docstring corrected.
- **D98 docs.** Bridge README (installation, maintenance and storage sections now point to agent-relay's Python
  runtime; the TS commands that remain), bridge CHANGELOG, `UPSTREAM.md`, agent-relay README if it names the TS CLI,
  CHANGELOG `[Unreleased]`.

## Requirements

0. Red first: a CLI test that `setup`, `doctor`, `status`, `prune`, `rollback`, `uninstall` are refused with the usage
   text and exit 2; an MCP test that `initialize` reports `serverInfo.name` `agent-relay`.
1. `retire` unchanged: the existing retire behaviour test (through the built `dist/cli.js`, as the Python script runs
   it) passes, `--keep-backlog` keeps the backlog; `native_collaboration_retire.py` tests stay green.
2. `npm ci --ignore-scripts` succeeds on the renamed package (the runtime install path); `scripts/validate.sh` green on
   Python 3.9, 3.10, 3.14; CI green.
3. Python: doctor's parser has no `--claude-settings`; everything else in doctor unchanged.
4. Live check in a `mktemp -d` HOME: v0.4.0 runtime and hosts → `upgrade --confirm` → probe 10 tools, doctor all ok,
   `native_collaboration_retire.py --name <x> --confirm-retire` retires an identity with no backlog; temporary HOME
   to the Trash.

## Boundaries

- Always: the sealed state root in tests; manifest and `UPSTREAM.md` with every bridge change.
- Ask first: the real `~/.agent-relay`, `~/.claude`, `~/.codex`; renaming `clientType` or `DATA_DIR_NAME`; any change to
  `retire` behaviour; new dependencies.
- Never: push without approval.

## Success criteria

The TS CLI offers only `retire` and `help` and the Python retire path still works; the server introduces itself as
`agent-relay`; no install, upgrade or uninstall code remains outside Python; a host installed by 0.4.0 upgrades with
doctor all ok.

## Open questions

None. Accepted by the user on 2026-10-08: assumptions 1–7 (1 and 2 include the user's choices: only `retire` and
`help`, package `agent-relay-bridge`), D95–D98.
