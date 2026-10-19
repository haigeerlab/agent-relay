# Spec: script-access

## Objective

Only module of 0.9.0 (runtime CLI, installer, docs). A request relayed on 2026-10-20 from an upper layer: its patrol
runs every five minutes (read every mailbox's state, compute actions, wake stopped sessions, remind owners, notify the
user), but today only a model inside one desktop session can run it, because reading the mailbox and sending go
through agent-relay's MCP tools only. When that session stops, the patrol stops. The upper layer already has a
launchd job; it lacks a way for a script to read agent-relay and to send.

Readers: the user; the round-2 coordinator (review, acceptance); the requesting upper layer (consumer of the new
commands); the Spec Guard owner (interface 2.8 is within its accepted `>=1.0,<3.0`).

## What exists today (main 0c1197c, v0.8.5)

- The runtime CLI `~/.agent-relay/runtime/dist/cli.js` knows `retire` and `help` only (`cli-logic.ts` `CLI_COMMANDS`);
  it needs `BRIDGE_DB_PATH`. `native_collaboration_retire.py` runs it with the node it was given.
- Host entries (Claude `~/.claude.json`, Codex `~/.codex/config.toml`) start `server.js` with an absolute node path
  resolved at attach time (`native_collaboration_adapters.py` `shutil.which("node")`). A launchd agent has
  `PATH=/usr/bin:/bin` and cannot read `~/Documents`, `~/Desktop`, `~/Downloads` (measured by the upper layer: exit
  126), so neither the plugin's hooks nor PATH's node are usable from launchd.
- `interface.json` declares one command, `status`, relative to the plugin root (`relay_status.py`).
- Identity (identity-check D37, D38): a name belongs to the host session that registered it — a Claude session is
  verified from the bridge's environment, a Codex task by having registered in this bridge process. A script is
  neither, so it has no name it may send as.
- `bridge_agents`, `bridge_outbox` and `bridge_sessions` are MCP handlers in `server.ts`; the store's reads call
  `expireDue` (a write) first, and opening a `BridgeStore` may migrate the schema.
- Wakes are dispatched by the `WakeDispatcher` inside each bridge process (every 2 s). A Claude session is woken only
  while its process runs (host differences H1, H4); a Codex task only while the ChatGPT app has it loaded (D200).

## Assumptions (accepted by the user 2026-10-20)

1. **Launcher.** `install` and `upgrade` write `~/.agent-relay/bin/agent-relay` (0700, owner only): a `/bin/sh` script
   with the absolute node path and runtime path written in, and `BRIDGE_DB_PATH` / `XDG_DATA_HOME` set, that runs
   `dist/cli.js`. It reads nothing under `~/Documents`, needs no PATH entry, and works when the plugin was installed
   from a development checkout. `uninstall` removes it; `rollback` rewrites it for the previous runtime.
2. **Four commands, declared in `interface.json`**: `agents`, `outbox <name>`, `sessions`, `send`. Each prints one JSON
   object on stdout and exits 0; when the runtime is not installed, is mid-swap, or the mailbox schema does not match,
   it exits non-zero with one sentence on stderr (as `status`'s `setup`).
3. **Reads are read-only**: `agents`, `outbox`, `sessions` open the mailbox read-only — no registration, no read
   receipt, no acknowledgement, no expiry sweep, no migration. Their output is produced by the same code as the MCP
   tool (`bridge_agents` without parameters, `bridge_outbox {agent}`, `bridge_sessions`), field for field and under the
   interface version; `sessions`' `thisSession` and `codexSessionId` are `null` (a script is not a session). A message
   past its timeout that no bridge has swept yet may show as not expired for up to the sweep interval (2 s).
4. **`send`**: from a script identity (assumption 5) to a registered recipient; the body from `--body-file <path>` or
   stdin, never argv; `--expects-reply`, `--reply-to`, `--thread`, `--also-answers`, `--withdraws`,
   `--idempotency-key`, `--no-wake`. Same effect as `bridge_send` (warnings, `closed`, `skipped`). After storing, the
   command dispatches that message's wake once itself before exiting (no waiting for another bridge).
5. **Script identities.** `register-script-identity <name> --confirm` (run by the user in a terminal, or by a session
   only with the user's explicit agreement) records the name with host `{app: "script", sessionId: <name>}` and no
   wake binding. `send --from` accepts only a script identity; no session can act as one (its recorded host is not
   theirs) unless the user agrees to `takeover`. A script identity is never woken; replies to it are read by the next
   patrol through `outbox`/`agents`. Retiring one is the existing retire script.
6. A new module, full flow; released as **0.9.0**; interface **2.8** (additions only); acceptance as the requester
   listed (below).

## Decisions

- **D240 the launcher.** `native_collaboration_runtime.py` writes `bin/agent-relay` after a successful install or
  upgrade, with the node it built with resolved to an absolute path (`shutil.which` on the given `node`, refusing a
  relative result), and verifies it by running `agent-relay --version`. `doctor` gains a `script-launcher` check: the
  file exists, is 0700, points at the current runtime, and its node exists. Rollback rewrites it; uninstall removes it.
- **D241 commands share the MCP code.** `server.ts`'s handlers for the three reads are moved into pure functions
  (`agentsView`, `outboxView`, `sessionsView`) taking a store and a context; the MCP tools and the CLI call the same
  functions. A test compares CLI output with the MCP result for the same mailbox, field by field.
- **D242 read-only store.** `BridgeStore` gains a read-only open (`{ readOnly: true }`): SQLite `mode=ro`, no migration
  (a schema other than the runtime's is an error), and every `expireDue` skipped. Presence lookups (Claude registry,
  ChatGPT IPC with the 2 s cap) run as in the MCP tool; they read nothing in protected folders.
- **D243 `send` and its wake.** `send` uses the store's `deliver` inside one process, then runs the dispatcher's
  `flush` once for that message (Claude peer socket or ChatGPT IPC), and prints the same object `bridge_send`
  returns, with `wake` as left after that flush. `--no-wake` stores without a ping (as `wake: false`).
- **D244 script identity.** Host app `"script"` is a new recorded host value; no schema change (the column has no
  check), so mailbox schema stays 7. `CallerIdentity` treats a recorded `script` host as owned by no session; the CLI
  owns exactly the script identities. Presence for a script identity is `unknown` with detail "script identity". A
  0.8.x bridge reading such a row already refuses to act as it (recorded host differs, D38) and shows its presence as
  `not-loaded` or `unknown`; the CHANGELOG says so.
- **D245 interface 2.8.** `interface.json` gains `"script": {"agents": [...], "outbox": [...], "sessions": [...],
  "send": [...]}`, each an argv whose first element is `~/.agent-relay/bin/agent-relay` (`~` is `$HOME`); `status`
  unchanged. The interface document lists the commands, their output (the MCP tools' rows), exit codes, the read-only
  promise and the script identity.

## Requirements

1. Red first, `bridge/test/script-access.test.ts` (new): read-only open refuses writes and skips migration and expiry;
   `agents`/`outbox`/`sessions` output equals the MCP tools' for the same mailbox (fake ChatGPT socket, fake Claude
   registry); mailbox unchanged after the reads (row counts, `read_at`, acknowledgements, `last_seen`); `send` refuses a
   non-script `--from`, reads the body only from file or stdin, returns `bridge_send`'s object, and pings a bound fake
   Claude session once; `register-script-identity` without `--confirm` changes nothing; a session cannot register or
   act as a script identity without `takeover`.
2. Hooks tests: the launcher is written on install and upgrade, rewritten on rollback, removed on uninstall, runs
   under `env -i PATH=/usr/bin:/bin HOME=$HOME`, and fails with one stderr sentence when the runtime is absent or
   mid-swap; `doctor`'s `script-launcher` check.
3. `interface.json` 2.8, `test_packaging`, `relay_status.py` docstring, `docs/collaboration-interface.md`, README
   (a short "scripts and launchd" section), `UPSTREAM.md` row and manifest, `bridge/CHANGELOG.md`, CHANGELOG.
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; CI green.

## Boundaries

- Always: tests first; reads never write; the body never on argv.
- Ask first: letting `send` act as any non-script identity; any automatic registration of a script identity.
- Never: wake a stopped Claude session by other means; read conversation content; store the body outside the mailbox.

## Acceptance (after 0.9.0, coordinator with the user's agreement)

- Under `env -i PATH=/usr/bin:/bin` (or a launchd job), the three reads match the MCP tools at the same moment, and the
  mailbox is unchanged before and after (unread counts, receipts, registrations).
- With a test script identity, `send` to a wake-bound test session wakes it and delivers the body; `bridge_outbox`
  shows the message.
- With the plugin installed from a checkout under `~/Documents`, launchd runs the reads and `send` with exit 0.
- `doctor` `script-launcher` ok; Spec Guard accepts 2.8.

## Open questions

None left; resolved by the user 2026-10-20, as proposed:

1. A script identity follows the normal idempotency rules (no `bridge`-style folding by key only).
2. Only the CLI registers a script identity (`register-script-identity --confirm`); no MCP path.
