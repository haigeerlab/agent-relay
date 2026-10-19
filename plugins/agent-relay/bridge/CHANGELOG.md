# Changelog

## agent-relay 0.8.4

`codex-approval-presence` rework after the round-2 post-merge review: a follower frame over 8 MiB is discarded without
buffering it and without dropping the connection, so `codexTaskPresence` still sends `following: false` (before, the
connection was destroyed and the unfollow never went out). Docs: a `waiting-input` from `item/tool/requestUserInput`
has no `since`.

## agent-relay 0.8.3

Codex waiting states (module `codex-approval-presence`, D232–D236), schema 7 unchanged: for a Codex task the ChatGPT app
has loaded, presence follows the task once through the app's local connection, reads only the `method` (and start time)
of its pending requests, unfollows, and reports `waiting-approval` or `waiting-input` in `bridge_agents`, the
`bridge_send` warning and `bridge_outbox` `awaitingReply`, within the 2 s cap; anything unexpected reads `running`.
`CodexIpc` gains `broadcast()` and `nextChange()`; no conversation content is kept and no prompt is ever answered.

## agent-relay 0.8.2

Doubtful deliveries (module `accepted-unread-notice`, D228–D231), schema 7 unchanged: a Codex ping the ChatGPT app
accepted five minutes ago whose message is still unread and unacknowledged is told to the user once (a desktop notice
naming both possible causes: a closed mailbox connection, or a read before the task registered again in a new bridge
process) and to the sender once (a `bridge` message); `bridge_outbox` and `bridge_wake_status` show `wake.doubt`,
`bridge_agents` shows `waiting.doubtfulIds`, until the recipient reads or acknowledges it.

## agent-relay 0.8.1

Listing and status polish (module `agents-view-polish`, D223–D227), schema 7 unchanged: `bridge_agents` pages when
asked (`includeRetired`, `maxChars`, `afterName`) and keeps retired entries short, a plain call stays whole; message
status by id answers any caller; a running Claude presence says `activity` busy or idle; the ChatGPT app is asked for at
most 2 s, so a listing or a send to a task that is not open no longer waits ten seconds.

## agent-relay 0.8.0

Requests close as they are really handled (module `request-closing`, D216–D222), mailbox schema 7: one answer can
close further requests addressed to its sender (`bridge_send` `alsoAnswers`), a sender can withdraw its own requests
(`withdraws`, recorded as withdrawn, not answered), the result echoes `closed`, and another sender whose request was
answered this way gets one notice and may read the answer. `awaitingReply` and `owesReplies` no longer count closed
requests.

## agent-relay 0.7.2

Delivery-failure explanations follow the real cause (module `expiry-notice-reason`, D215), schema 6 unchanged: a
Claude ping that expired because the recipient session was not running is explained as "not running; open that
session" instead of a Bypass permissions / `crossSessionInbound` hold, in the notice, `bridge_wake_status` and the
send-time warning; only a `held` ping or Claude's own expiry receipt counts as a hold.

## agent-relay 0.7.1

Three fixes from a usage report (modules `codex-identity-recovery`, `reply-own-message-guidance`, `read-own-sent`),
schema 6 unchanged: a Codex task whose bridge process was replaced is told to register its own name again, without a
takeover, and the server instructions say so and say to stop on `Transport closed`; a sender pointing `replyTo` at its
own message is told how to add to it (its thread, or "Addendum to #N:"); `bridge_inbox` `messageId` reads back the
caller's own sent messages with `direction`, recording no read, and a refused id says why and whom to ask.

## agent-relay 0.7.0

Requests that expect an answer (module `awaiting-reply-view`): mailbox schema 6 adds `messages.expects_reply`;
`bridge_send` takes `expectsReply`, `bridge_outbox` `awaitingReply` lists the open requests with `waitingSeconds` and
the recipient's presence, and `bridge_agents` shows `owesReplies`. Changes after 0.5.0 are in agent-relay's own
CHANGELOG and in `UPSTREAM.md`.

## agent-relay 0.5.0

agent-relay removed the Codex workers from its vendored copy (module `orchestrator-removal`): `ask_codex`,
`review_with_codex`, `bridge_orchestrate_codex`, `bridge_continue_codex`, `bridge_orchestration_wait`,
`bridge_orchestration_status` and the `bridge_retire` tool are gone, and so are run recovery, run-file pruning,
`BRIDGE_WORKTREE_ROOT` and `npm run smoke:orchestrator`. The server registers only the ten mailbox tools; retiring
stays the CLI `retire`. The orchestration tables stay in the schema, unread. Module `legacy-cli-cleanup` then cut the
CLI down to `retire` and `help` (setup, doctor, status, demo, prune, backup, rollback and uninstall are gone; agent-relay's
Python runtime does those) and renamed the package `agent-relay-bridge`; the server introduces itself as `agent-relay`.
The entries below are upstream history.

## 0.4.0

Driven by field use of the 0.3 mailbox with dozens of agents: Claude pings that expired instead of waking anyone, direct messages that were never acknowledged, messages sent to names that never registered, threads that outgrew MCP output limits, and Codex workers that were rarely used because calls outlived host timeouts.

### Safety

- Resumed Codex turns no longer inherit the user's `config.toml` sandbox. Before this release, `bridge_continue_codex` ran `codex exec resume` without a sandbox setting. On a machine whose default is `danger-full-access`, resumed workers ran unsandboxed. The sandbox is now pinned on every turn, and a live smoke test checks Codex's own rollout.
- `review_with_codex` runs in a read-only sandbox instead of relying on its prompt, and warns if the workspace changed.
- The mailbox, its WAL/SHM files, backups and Codex turn files are owner-only (`0600`/`0700`). Existing files are tightened at startup, and `doctor --fix` fixes them on demand.
- `BRIDGE_CODEX_CONFIG` can tune worker model settings. It can never change sandbox, approval or environment policy.
- Dependencies updated past published advisories in `fast-uri` (high) and `qs` (moderate), both pulled in by the MCP SDK.

### Delivery

- Root cause of expiring Claude pings documented: Claude Code holds cross-session messages for sessions in Bypass permissions (`crossSessionInbound`), and the desktop app has no approval surface for them. The bridge explains this in `bridge_send` warnings, `bridge_wake_status` and `doctor`, and never changes the setting.
- Failed, expired and held pings produce one automated notice to the sender, coalesced per recipient per half hour and loop-proof.
- Pings to a Codex task that is merely busy are kept for 24 hours instead of expiring after one.
- `wake: "auto"` binds the current conversation without copying session IDs. A binding moves automatically when its previous Claude session is no longer running.
- Opt-in Claude Code channel delivery (`BRIDGE_CLAUDE_CHANNEL=1`) for terminal sessions launched with channel flags.

### Mailbox

- `bridge_send` rejects unknown and retired recipients with "did you mean" suggestions (`allowUnregistered` overrides), and warns when a recipient is idle, unreachable or failing pings.
- New `bridge_outbox` shows what recipients have not handled, with ping state.
- New `bridge_retire` and CLI `retire`/`prune` close out finished agents. Their backlog is acknowledged with a recorded reason, history is kept, and active senders are told what was closed.
- `bridge_inbox`, `bridge_thread` and `bridge_wait` return pages sized to stay inside MCP output limits, with cursors, totals and an optional preview mode. Threads open at the newest messages.
- Re-registering without capabilities keeps the existing list. Agents' last activity is tracked from real usage.
- `bridge_wait` filters by sender and thread in SQL instead of re-reading the whole backlog on every poll.

### Codex workers

- Calls wait up to `waitSeconds` (default 240) and then return `running_codex`. The finished result is posted to the coordinator's mailbox exactly once. New `bridge_orchestration_wait` fetches it from any process.
- Codex turns run as detached processes writing to files. Session IDs are saved as soon as they appear. Runs whose bridge process exited are adopted, finished from their files or marked interrupted, and delivered.
- Worktrees live outside the repository. Runs warn when the main checkout has uncommitted changes, and `includeUncommitted` copies them in.
- Every result includes the bridge's own `observedChanges`.
- The project path and coordinator default to the current session's project and agent.

### Operations

- Versioned schema (`PRAGMA user_version`) with additive migrations, a backup before any migration, and compatibility with 0.3 processes still running.
- Daily mailbox backups (seven kept). Codex event streams are pruned after 30 days; result envelopes are kept.
- `setup` installs smoke-tested runtime versions behind an atomically switched `current` link, edits Codex's config in place (keeping per-tool approvals, with a backup) and sets a 300-second Codex tool timeout. New `rollback`, `backup`, `retire` and `prune` commands, and a fuller `doctor`.
- Setup keeps the Node.js binary already registered (or `--node PATH`) and smoke-tests with it, and registers through the newest desktop-bundled Claude Code instead of a possibly stale `claude` on `PATH`.
- Broadcasts reach agents that were registered when they were sent; late joiners no longer inherit weeks-old broadcasts as unread.
- `scripts/mailbox-request.ts` never runs development source against the live mailbox; live requests go through the installed runtime.
- `demo` retires its two demo agents when it finishes.
- Atomic builds: `dist/` is swapped in whole, never deleted first.
- Type checking now covers tests and scripts. The live smoke test runs fully isolated.

## 0.3.0

- Experimental background pings between existing Claude and Codex conversations on macOS: `bridge_register` binds an agent to an exact app session, and `bridge_send` pings a bound recipient through its app's local interface.
- Durable wake jobs committed with the message, idempotent sends that never ping twice, and `bridge_wake_status` receipts that keep delivery separate from acknowledgement.
- `bridge_sessions` discovers live Claude sessions. Quiet sends (`wake: false`), broadcasts and self-messages never ping.
- An explicit-database MCP client for isolated wake testing.

## 0.2.0

- One-command setup from GitHub with automatic Claude and Codex MCP registration.
- A stable per-user runtime installation, with no pasted absolute paths.
- `doctor`, `status`, `demo` and safe `uninstall` commands.
- `ask_codex` and read-only `review_with_codex` MCP tools.
- Three user-invocable skills plus a Codex teammate definition.
