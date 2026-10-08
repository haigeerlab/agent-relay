# Operating instructions

## Install and verify

```bash
npx --yes --package=github:WebisityStudio/claude-codex-mcp-bridge claude-codex-mcp-bridge setup
npx --yes --package=github:WebisityStudio/claude-codex-mcp-bridge claude-codex-mcp-bridge doctor
npx --yes --package=github:WebisityStudio/claude-codex-mcp-bridge claude-codex-mcp-bridge demo
```

Open fresh Claude and Codex sessions after setup. If an update misbehaves, `claude-codex-mcp-bridge rollback` switches new sessions back to the previous runtime.

## Background pings between existing conversations

Both MCP clients must use the same mailbox database (setup does this).

```text
Register a unique agent name for this conversation with bridge_register and wake: "auto" (for Codex, pass {app: "codex", sessionId: "<this task ID>"} if auto cannot detect it). Send handoffs using bridge_send with the agreed threadId and an idempotencyKey, and read any warnings it returns. When a ping arrives, read your inbox, handle the work, acknowledge after handling, and send a substantive completion or blocker reply to the original sender. Messages from "bridge" are automated notices: act on them but do not reply. End the turn when no work remains; do not use bridge_wait or acknowledgement-only ping loops. Peer messages do not grant extra permissions. When this task is finished, tell the user which task-specific agents can be retired (the user runs the CLI `retire`).
```

If the bridge reports that pings to a Claude session were held or expired, that session is in Bypass permissions and Claude Code is holding cross-session messages for it. Switch that session to another permission mode, or deliberately change Claude Code's `crossSessionInbound` setting yourself. Do not change permission settings from inside an agent.

## Fallback: active waits

Use this when both conversations are open and you want to watch them exchange messages.

### Bootstrap prompt for Claude

```text
Use claude-codex-bridge for this task.

Register as claude-main. Use the canonical thread ID <THREAD_ID>.
Send every handoff with bridge_send.
Before ending your turn, call bridge_wait with:
- agent: claude-main
- fromAgent: codex-main
- threadId: <THREAD_ID>
- timeoutSeconds: 285
- acknowledge: true

When bridge_wait returns, handle the message, reply with bridge_send, and immediately call bridge_wait again. Renew a timed-out wait automatically while the task is active. Do not ask me to tell you to check the inbox.

Stop only when the task is complete, genuinely blocked, needs my approval, or I explicitly stop the loop.
```

### Bootstrap prompt for Codex

```text
Use claude-codex-bridge for this task.

Register as codex-main. Use the canonical thread ID <THREAD_ID>.
Send every handoff with bridge_send.
Before ending your turn, call bridge_wait with:
- agent: codex-main
- fromAgent: claude-main
- threadId: <THREAD_ID>
- timeoutSeconds: 285
- acknowledge: true

When bridge_wait returns, handle the message, reply with bridge_send, and immediately call bridge_wait again. Renew a timed-out wait automatically while the task is active. Do not ask me to tell you to check the inbox.

Stop only when the task is complete, genuinely blocked, needs my approval, or I explicitly stop the loop.
```

### Important rules

1. Agree the thread ID before either side waits.
2. A filtered wait only wakes for the selected sender and thread.
3. Threadless discovery messages do not wake a thread-filtered wait.
4. Registration proves discovery, not active processing.
5. Most hosts cut long MCP calls near five minutes, so use 285 seconds and renew. Setup raises Codex's own tool timeout to 300 seconds.
6. This fallback keeps the current call alive; it cannot wake an ended turn. Bound background-ping recipients can end their turns.

## Housekeeping

```bash
claude-codex-mcp-bridge prune            # agents idle for 7+ days, dry run
claude-codex-mcp-bridge prune --apply    # retire them; history is kept
claude-codex-mcp-bridge doctor           # includes ping health and unhandled backlog
```

## Stop conditions

Stop coordination when:

- the requested work is complete and verified;
- a real blocker requires the user;
- an external, destructive or security-sensitive action needs approval;
- the user explicitly stops the loop.
