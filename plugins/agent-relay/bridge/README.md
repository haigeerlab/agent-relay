<p align="center">
  <a href="https://www.webisitystudio.co.uk/">
    <img src="assets/webisity-studio-logo.svg" width="180" alt="WebiSity Studio logo">
  </a>
</p>

<h1 align="center">Claude Codex MCP Bridge</h1>

<p align="center">Built by <a href="https://www.webisitystudio.co.uk/">WebiSity Studio</a></p>

[![CI](https://github.com/WebisityStudio/claude-codex-mcp-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/WebisityStudio/claude-codex-mcp-bridge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

<p align="center">
  <img src="assets/bridge-demo.gif" alt="Claude Codex MCP Bridge send, wait, wake and acknowledge demo" width="900">
</p>

A local MCP bridge for Claude Code and OpenAI Codex. It gives a team of Claude and Codex conversations a durable SQLite mailbox and background pings between them.

> **agent-relay copy.** agent-relay 0.5.0 removed the upstream Codex workers (`ask_codex`, `review_with_codex`,
> `bridge_orchestrate_codex`, `bridge_continue_codex`, `bridge_orchestration_wait`, `bridge_orchestration_status`) and the
> `bridge_retire` tool; the server offers only the ten mailbox tools below. Retire agents with the CLI `retire`. Tag
> `v0.4.0` of agent-relay has the last copy of the removed code (module `orchestrator-removal`, see `UPSTREAM.md`).

```text
Claude Code ──stdio MCP──┐
                         ├── local SQLite WAL store (private to your user)
Codex       ──stdio MCP──┘
```

The default mode has no account, cloud relay, HTTP server or listening network port.

## Why

Plain MCP tools are request-response. Writing a message to a mailbox does not automatically start a new model turn in another chat. The bridge supports two patterns:

1. **Background pings (experimental, macOS):** bind each conversation once with `wake: "auto"`; a durable message pings an idle recipient through its app's local interface. If a ping cannot be delivered, the sender is told automatically. See [background setup and limits](docs/BACKGROUND-WAKE.md).
2. **Active waits:** agents without pings use `bridge_wait` before going idle. The pending call returns when a matching message arrives.

See [INSTRUCTIONS.md](INSTRUCTIONS.md) for copy-paste prompts.

## Features

- Local SQLite WAL mailbox with versioned, backed-up migrations and daily backups
- Direct messages, broadcasts, stable thread IDs and idempotency keys
- Recipient-scoped acknowledgements, an outbox of what others have not handled, and agent retirement that closes finished work with a recorded reason
- Recipient checks: unknown names are rejected with "did you mean" suggestions, and senders get warnings when a message is unlikely to be picked up
- Output paging so large inboxes and threads never overflow an MCP result
- Optional background pings with delivery receipts, a 24-hour window for busy recipients and automatic notices to the sender when a ping fails
- Installed, upgraded, checked and uninstalled by agent-relay's Python runtime

## Tools

| Tool | Purpose |
|---|---|
| `bridge_register` | Register an agent; `wake: "auto"` binds this conversation for background pings |
| `bridge_send` | Save a message, ping a bound recipient, and warn about delivery risks |
| `bridge_inbox` | Read unread messages in pages that fit the host's output limit |
| `bridge_ack` | Acknowledge handled messages without deleting history |
| `bridge_wait` | Keep the current turn open until a matching message arrives |
| `bridge_thread` | Read a thread, newest page first, with cursors both ways |
| `bridge_outbox` | See which of your messages recipients have not handled, and why |
| `bridge_agents` | List agents with unread counts, last activity and ping health |
| `bridge_sessions` | Discover live Claude sessions and this conversation's own session |
| `bridge_wake_status` | Inspect ping outcomes separately from acknowledgements |
## Requirements

- Node.js 22.5 or newer
- Claude Code
- OpenAI Codex

The mailbox works anywhere Node and both MCP clients run.

Core tests run on macOS, Linux and Windows in GitHub Actions. Background pings and the live Claude Desktop plus Codex Desktop workflow were developed and verified on macOS.

## Install

agent-relay installs this copy; the upstream `setup` command was removed (module `legacy-cli-cleanup`). From the
agent-relay plugin root, after the user agrees:

```bash
python3 hooks/native_collaboration_runtime.py install          # build and probe the runtime under ~/.agent-relay/runtime
python3 hooks/native_collaboration_adapters.py install-claude  # add the Claude MCP entry
python3 hooks/native_collaboration_adapters.py install-codex   # add the Codex entry (300-second tool timeout)
python3 hooks/native_collaboration_runtime.py doctor
```

See agent-relay's README for upgrades, uninstalling and the steps that need a closed session.

### From a checkout (development)

```bash
npm ci
npm run check
```

## Background pings

Bind each conversation once:

```json
{"agent": "review-claude", "wake": "auto"}
```

Claude sessions are detected automatically. For Codex, pass `{"app": "codex", "sessionId": "<task ID>"}` when `auto` cannot see the task ID. Then send normally, acknowledge after handling, and end the turn when no work remains. See [the background wake guide](docs/BACKGROUND-WAKE.md) for receipt states and limits.

When a ping cannot be delivered, the sender receives one automated notice from `bridge` explaining why and what to do. The most common cause is Claude Code holding messages for sessions that run in Bypass permissions (its `crossSessionInbound` setting). The bridge explains this but never changes that setting.

## Fallback: active waits

Pick one canonical thread ID, register unique names, send with `bridge_send`, and wait with:

```json
{
  "agent": "claude-main",
  "fromAgent": "codex-main",
  "threadId": "invoice-review-001",
  "timeoutSeconds": 285,
  "acknowledge": true
}
```

Most MCP hosts cut tool calls near five minutes, so waits are capped at 290 seconds. Renew a timed-out wait while the task is active. A filtered wait only wakes for the exact sender and thread.

## Maintenance

From the agent-relay plugin root:

```bash
python3 hooks/native_collaboration_runtime.py doctor              # runtime, probe, mailbox, host entries, pings
python3 hooks/native_collaboration_runtime.py status
python3 hooks/native_collaboration_runtime.py upgrade --confirm   # every session using the mailbox closed first
python3 hooks/native_collaboration_retire.py --name <agent> --confirm-retire
python3 hooks/native_collaboration_runtime.py uninstall --confirm # keeps mailbox history
```

The bridge's own CLI (`agent-relay-bridge`, not on `PATH`) keeps only `retire <agent> [--note TEXT] [--keep-backlog]`,
which the retire script runs with `--keep-backlog`.

Retiring never deletes messages. Closed messages keep their history and a note saying why, recently active senders get one notice listing what was closed. The name stays retired: `bridge_register` refuses it unless the call passes `reactivate: true` (agent-relay change).

## Storage

```text
~/.agent-relay/runtime/mailbox/bridge.sqlite     mailbox (owner-only)
~/.agent-relay/runtime/mailbox/backups/          pre-migration and daily backups (7 kept)
~/.agent-relay/runtime/                          the installed runtime (upgrade keeps the previous one beside it)
```

`AGENT_RELAY_HOME` moves the whole state root. agent-relay's host entries pass `BRIDGE_DB_PATH`, so every MCP process uses the same database. Set `BRIDGE_BACKUPS=0` to disable daily backups.

Schema changes are additive and versioned. Before migrating an existing mailbox, the bridge writes a backup. Older bridge processes that are still running keep working against the migrated database.

## Honest limitations

- Background pings use observed local app interfaces, not public APIs. They need the app and its session host running.
- Claude Code holds pings for sessions in Bypass permissions, and the desktop app has no prompt to approve them, so they expire. Sessions in other permission modes, or a deliberate `crossSessionInbound: "accept"` setting, avoid this. The sender is notified either way.
- Claude Code channels (`BRIDGE_CLAUDE_CHANNEL=1`) are supported as an opt-in push path, but Claude Code only listens when launched with its channel flags, which the desktop app does not expose.
- Codex does not expose its task ID to MCP servers in every version, so `wake: "auto"` may need the ID passed explicitly.
- Registration proves discovery, not active processing. Acceptance of a ping is not completion of the work.
- The transport is local to one machine.

## Safety

- No credentials are stored by this project. The Claude wake adapter reads only the addressed inbox's published peer token into memory and never logs it. It never uses child tokens or claims a permission mode.
- The mailbox and its backups are owner-only. Messages are stored unencrypted, so do not send secrets through the mailbox.
- Messages from `bridge` are automated notices. Agents are told not to reply to them, and notices never trigger further notices.

## Development

```bash
npm run typecheck   # src, tests and scripts
npm test
npm run build       # compiles into dist.next/ and swaps it in
npm run check       # all of the above
npm audit --omit=dev --audit-level=high
```

The suite covers socket framing, identity and permission boundaries, migrations from 0.3 databases and compatibility with running 0.3 processes, ping persistence, crash recovery and failure notices, mailbox routing, addressing checks, retirement, paging, independent MCP processes and the `retire` CLI.

## Related work

This is not the only Claude/Codex bridge. See [docs/ALTERNATIVES.md](docs/ALTERNATIVES.md) for a comparison with Claude Channels bridges, ACP delegation tools and general agent mailboxes.

## License

MIT
