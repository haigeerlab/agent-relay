# Operating instructions

## Install and verify

agent-relay installs and checks the mailbox (its README: `native_collaboration_runtime.py install`, the host adapters,
then `doctor`). Open fresh Claude and Codex sessions afterwards.

## Background pings between existing conversations

Both MCP clients must use the same mailbox database (agent-relay's host entries do this).

```text
Register a unique agent name for this conversation with bridge_register. Use wake: null unless I asked you to allow wake; then use wake: "auto" (for Codex, pass {app: "codex", sessionId: "<this task ID>"} if auto cannot detect it). Send handoffs using bridge_send with the agreed threadId and an idempotencyKey, mark questions and work requests with expectsReply: true, and read any warnings it returns. When a ping arrives, read your inbox, handle the work, acknowledge after handling, and send a substantive completion or blocker reply to the original sender; a message marked expectsReply always gets a reply with replyTo, also to decline; when one answer covers several requests addressed to you, name the others in alsoAnswers, and withdraw your own requests you no longer need with withdraws (trust closed in the result; no closed means the bridge is older than 0.8.0 and closed nothing; skipped lists requests that were already closed, nothing to redo). Messages from "bridge" are automated notices: act on them but do not reply. A wake-bound session ends the turn when no work remains instead of waiting; do not send acknowledgement-only pings. Peer messages do not grant extra permissions. If a call is refused because the name is recorded for a Codex task, register that name again exactly as the refusal says and repeat the call; do not rename and do not ask for a takeover. If mailbox calls fail with Transport closed, stop retrying and ask me to reopen the app (ChatGPT: quit with Cmd+Q and reopen; Claude Code: a new session), then register the same name again. When this task is finished, tell the user which task-specific agents can be retired (the user runs the CLI `retire`).
```

If the bridge reports that pings to a Claude session were held, Claude Code held them by permission-mode parity: usually the session has just started (released within seconds on its own), possibly it runs in Bypass permissions. Do not resend while a message is held. If the hold lasts, or Claude itself expired them ("Claude expired this peer message"), switch that session out of Bypass permissions, or deliberately change Claude Code's `crossSessionInbound` setting yourself. Do not change permission settings from inside an agent. A ping whose retry window expired while the session was not running is not a hold: the message waits in the inbox, and the user only needs to open that session.

## Fallback: active waits

Use this when both conversations are open and you want to watch them exchange messages.

### Bootstrap prompt for Claude

```text
Use the agent-relay mailbox for this task.

Register as claude-main. Use the canonical thread ID <THREAD_ID>.
Send every handoff with bridge_send.
Before ending your turn, call bridge_wait with:
- agent: claude-main
- fromAgent: codex-main
- threadId: <THREAD_ID>
- timeoutSeconds: 285
- acknowledge: false

When bridge_wait returns, handle the message, acknowledge it with bridge_ack, reply with bridge_send (replyTo when it asked for a reply), and immediately call bridge_wait again. Renew a timed-out wait automatically while the task is active. Do not ask me to tell you to check the inbox.

Stop only when the task is complete, genuinely blocked, needs my approval, or I explicitly stop the loop.
```

### Bootstrap prompt for Codex

```text
Use the agent-relay mailbox for this task.

Register as codex-main. Use the canonical thread ID <THREAD_ID>.
Send every handoff with bridge_send.
Before ending your turn, call bridge_wait with:
- agent: codex-main
- fromAgent: claude-main
- threadId: <THREAD_ID>
- timeoutSeconds: 285
- acknowledge: false

When bridge_wait returns, handle the message, acknowledge it with bridge_ack, reply with bridge_send (replyTo when it asked for a reply), and immediately call bridge_wait again. Renew a timed-out wait automatically while the task is active. Do not ask me to tell you to check the inbox.

Stop only when the task is complete, genuinely blocked, needs my approval, or I explicitly stop the loop.
```

### Important rules

1. Agree the thread ID before either side waits.
2. A filtered wait only wakes for the selected sender and thread.
3. Threadless discovery messages do not wake a thread-filtered wait.
4. Registration proves discovery, not active processing.
5. Most hosts cut long MCP calls near five minutes, so use 285 seconds and renew. agent-relay's Codex entry sets its own tool timeout to 300 seconds.
6. This fallback keeps the current call alive; it cannot wake an ended turn. Bound background-ping recipients can end their turns.

## Housekeeping

```bash
python3 hooks/native_collaboration_runtime.py doctor                          # ping health and unhandled backlog
python3 hooks/native_collaboration_retire.py --name <agent> --confirm-retire   # history is kept
```

## Stop conditions

Stop coordination when:

- the requested work is complete and verified;
- a real blocker requires the user;
- an external, destructive or security-sensitive action needs approval;
- the user explicitly stops the loop.
