# Background wake-up (experimental, macOS)

Background pings connect existing local app conversations. The model can end its turn. A small dispatcher inside every bridge MCP process delivers pending pings; no third model, scheduled AI task, WebSocket service, window navigation or simulated keyboard input is involved.

## Connect two conversations

Both MCP servers must use the same SQLite database (agent-relay's host entries configure this). Register each conversation once with a unique agent name:

```json
{"agent": "review-claude", "wake": "auto"}
```

`auto` binds the conversation hosting this bridge process. Claude Code exposes its session ID to MCP servers, so Claude sessions are detected automatically. Codex does not expose its task ID in every version; if `auto` reports that it cannot detect the session, pass it explicitly:

```json
{"agent": "review-codex", "wake": {"app": "codex", "sessionId": "<CODEX_TASK_ID>"}}
```

`bridge_sessions` lists live Claude sessions and shows `thisSession` when it is known. Claude accepts either the internal session UUID or its desktop bridge session ID.

Then call `bridge_send` normally. The mailbox message and its wake job commit in one SQLite transaction. Sending with the same sender/idempotency key returns the original message and cannot create another ping. A `wake:false` send, broadcast or self-message is silent.

Pings show the sender, message ID and a short preview in the recipient conversation. The complete message and delivery history remain in SQLite.

On a ping, read the named inbox, handle the work, then acknowledge it. Reply to the original sender on the same thread when complete, blocked, or needing a decision. End the turn when no work remains. Do not send acknowledgement-only pings.

Omitting `wake` from registration preserves the current binding. `wake: null` disables future pings and cancels pending ones. An agent name cannot silently move to another live conversation; unbind first or choose a new name. If the previously bound Claude session is no longer running, registering again from the new session moves the binding. Already dispatched input cannot be recalled.

## Delivery evidence

`bridge_wake_status` returns up to 100 recent jobs with a per-state summary, optionally filtered by agent.

| State | Meaning |
|---|---|
| pending | App unavailable or recipient mid-turn; eligible for retry |
| sending | One dispatcher owns this attempt |
| accepted | App confirmed admission or a new turn; the work is not necessarily done |
| read | A bridge inbox read fetched the message; acknowledgement is still separate |
| held | Claude retained the ping without admitting it to the model |
| refused | Unsupported protocol, or Claude declined, dropped or expired the message |
| unknown | Input may have arrived, but no positive receipt was received |
| cancelled | Recipient unbound, retired, or the message was acknowledged before dispatch |
| expired | The retry window elapsed; the mailbox message is preserved |

Dispatchers check for due jobs every two seconds, with per-job exponential backoff up to one minute. A ping for an unreachable recipient is kept for one hour. A ping for a Codex task that is merely busy is kept for 24 hours, because the app's own idle check makes later delivery safe. A closed MCP process leaves the outbox for the next one. Failed or lost confirmations after submission are never replayed automatically.

## When a ping fails, the sender is told

When a ping ends `refused`, `expired` or `held`, the bridge sends the original sender one automated message from `bridge`. It names the message, explains the cause and suggests next steps. The message itself stays unread in the recipient's inbox. Notices are coalesced to one per sender and recipient per half hour, are never sent to unregistered or retired senders, and a failed notice never produces another notice. Senders can see everything still unhandled with `bridge_outbox`.

`bridge_send` also warns at send time when the last three pings to a recipient failed, when a bound Claude session is not running, or when an unbound recipient has been idle for a day.

A Claude session can stop while idle (the Claude app stops idle sessions' processes), and a ping goes only to a live
process. Such a ping stays `pending` with `pendingReason: "offline"`, shown per message in `bridge_outbox` (a message
queued behind an earlier one to the same recipient shows that one's reason). After five minutes the user gets one
desktop notification per offline spell naming the session, how many messages wait and when the first was sent; it has
no message text and no click action. Opening the session lets the next retry deliver the messages.

A Claude session that may be running but cannot be pinged — several live sessions claim the recipient, or its local
inbox cannot be reached or fails the ownership checks — waits as `pendingReason: "unreachable"` instead. It is retried
and expires like an offline one, but it never raises the offline notice. Once any notice was attempted for a message
(Codex) or an offline spell (Claude), every later retry's detail keeps saying so; there is still only one notice.

When the ChatGPT app accepts the connection but does not answer about a Codex task, the ping waits as `offline` with
the detail that the app did not answer for this task, usually because it was not opened since the app started, and that
opening it delivers the message (a deleted task, or a wrong id, looks the same; then the task has to join again).
`bridge_agents` shows such a task as `presence: not-loaded`, a send warns about it, and the Codex notice says to open the
task in the ChatGPT app. A socket that cannot be reached at all still reads "Codex local connection unavailable".

A Codex ping the ChatGPT app accepted (it confirmed a new turn) can still go unread: the task's mailbox connection may
be closed ("Transport closed", common after an upgrade or after bridge processes were ended) while the app keeps the
task loaded, so `presence` still reads `running`. When such a message is still unread and unacknowledged five minutes
after the ping was accepted (pings accepted more than a day ago are left alone), the 30-second check tells the user once
with a desktop notification and the sender once with a `bridge` message, and `bridge_outbox`, `bridge_wake_status` and
`bridge_agents` mark the delivery as in doubt (`wake.doubt`, `waiting.doubtfulIds`) until the recipient reads or
acknowledges it. A read is recorded only for a name the calling bridge process has proven, so a task that reads in a new
bridge process before registering again is flagged too; the notice names both causes. Claude recipients are not
checked: a Claude session whose bridge goes away loses its process, which the offline notice already covers.

For a Codex task the ChatGPT app has loaded, presence also says whether it waits for the user: the bridge follows the
task once through the app's local connection, reads only the kind of each pending request (command, file change or
permission approval; a question for the user) and when it started, stops following, and reports `waiting-approval` or
`waiting-input` (all within the same 2 s cap; anything unexpected reads `running`). Nothing else of the conversation is
read or kept, and the bridge never answers a prompt: the user does, in that task.

A ping that expired while its recipient was away is pinged once more when the recipient comes back: when it registers
again, or when the 30-second check finds its Claude session running in a process that started after the expiry. Only
messages it has not read or acknowledged, and that have not expired themselves, are pinged again; the ping says when the
message was first sent so the recipient can check the request still applies. One process start does this at most once,
and the sender and the user are not told a second time.

## Why Claude pings expire

A Claude ping can expire for two different reasons. If the recipient session was not running for the whole one-hour retry window (the Claude app stops idle sessions), the ping expires with `pendingReason: "offline"`; the message stays in the inbox and the fix is to open that session. The bridge's notice, `bridge_wake_status` and the send-time warning say so and do not mention permissions. Only a ping Claude held, or that Claude itself reported as expired, is the permission-mode hold described below.

Claude Code gates cross-session input by permission mode. When the recipient session runs in **Bypass permissions** and the sender does not state a permission mode, the message is held for the user's approval (Claude Code calls this a permission-mode parity hold). A terminal session shows it for review. The desktop app has no approval surface for it, so it expires. Claude Code's `crossSessionInbound` setting controls this: `"accept"` delivers held messages.

The bridge does not state a permission mode, because it has none. Claiming one would let any local process inject input into a bypass session. So the options belong to the user:

- run recipient Claude sessions in a permission mode other than Bypass;
- approve held messages in a terminal session; or
- deliberately set `"crossSessionInbound": "accept"` in `~/.claude/settings.json`, accepting that local peers can then deliver messages to bypass sessions without review.

agent-relay's `native_collaboration_runtime.py doctor` reports ping health per bound identity. It never changes `crossSessionInbound`.

## Claude Code channels (opt-in)

Claude Code channels let an MCP server push events into the session that launched it. Set `BRIDGE_CLAUDE_CHANNEL=1` in the bridge's Claude MCP environment and start Claude Code with `--dangerously-load-development-channels server:agent-relay` (or `--channels` once the server is allowed). The bridge then declares the `claude/channel` capability. Pings for that session are pushed through the channel by the session's own bridge process, and other processes skip them while its heartbeat is fresh.

Channels are a research preview. Claude Code returns no receipt for channel events, so they are recorded as `unknown` until the recipient reads its inbox. The desktop app does not currently expose the launch flags, so this mode applies to terminal sessions.

## App interfaces and limits

These are observed local app interfaces, not stable public APIs:

- **Codex:** connects to the private app IPC socket, initializes as a bridge client, discovers the exact task's owner, and requires `supportsUntrustedAppInput`. A ping enters as an `untrusted_input` tool result through the native follower start-turn path. Existing model, permission and workspace settings are inherited. The native idle guard defers a ping while a turn is active.
- **Claude:** resolves a live process through the local session registry, checks the UID and UTC process start time, and uses its private messaging socket. Only the inbox's published peer authentication capability is used, in memory. Child tokens, bypass claims and permission overrides are never used. A private temporary reply socket receives correlated receipts.

The apps and their local session hosts must remain running. Launching a stopped app or resurrecting an absent Claude worker is not implemented. Unavailable sessions keep unread messages. Remote conversations and other machines are out of scope.

Claude's normal tool approvals still apply after waking. The bridge does not grant approval or change app security settings.

## Isolated verification

The test suite starts this repository's server against temporary databases; it never touches the live mailbox.

A short-lived client does not keep retrying after it closes. App-connected MCP servers keep the background dispatcher.

Because live clients run the runtime agent-relay installed, rebuilding a checkout never changes the bridge that running sessions use.

The regression suite uses temporary databases and real local sockets to cover identity checks, peer authentication, held and refused receipts, exact Codex targeting, untrusted input, fragmented frames, response loss, single ownership, crash recovery, busy and offline retry windows, sender notices, channel routing and duplicate suppression. No test requires an app account or sends a message to a real conversation.
