# Spec: presence-and-approval

## Objective

Round-2 findings A2 and A4 (coordinator, 2026-10-09):

- **A2.** Three background Claude sessions (default mode reading outside the project; acceptEdits running Bash) all
  stopped on a permission prompt. `claude agents` showed "blocked · permission prompt"; `bridge_agents` showed only
  "read, not acknowledged". Nobody told the user, so the work stalled until someone looked.
- **A4.** In `bridge_agents`, a stopped session and a session stuck on a prompt look exactly like a running one; only a
  send warns "not running".

The user's principle stands: the communication layer delivers, wakes and reports truthfully; it never approves
anything for the user. This module makes the directory say who is running, stopped or waiting for the user, and makes
sure the user hears when a mailbox session is waiting for their approval.

Readers: the user; the round-2 coordinator (acceptance after the batch).

## What exists today (main d32f861, 2026-10-09)

- `bridge/src/server.ts:478-502` `bridge_agents`: name, unread, last activity, `host` (Claude verified), `wake` target,
  `lastPing`, `waiting` (D77). No running state.
- Claude sessions: `~/.claude/sessions/<pid>.json` carries `status` and `statusUpdatedAt`; while a prompt waits it also
  carries `waitingFor`. Observed on this Mac: `{"status": "waiting", "waitingFor": "permission prompt"}` (session
  "每日检查安卓 Chrome N/N-1 是否就绪", waiting since 10:12). `claude-wake.ts` already reads these files and checks the
  owner process (`liveOwner`: same uid, same process start time); `server.ts:40` `isClaudeSessionLive`.
- A background session whose process is gone still shows in `claude agents` (observed: "播放器项目生产级评估",
  `state: blocked`, no pid).
- Codex: `thread-owner-discovery` over the Codex IPC socket says whether a thread has a connected owner (used by
  `codex-wake.ts`). No signal for "waiting for approval" is known.
- doctor's `wake-bindings` check already reports Claude sessions whose `status` is `waiting` (`test_doctor.py:81`).
- Notices on this Mac: `notify.ts` (D67, D89), deduplicated per key under `<mailbox dir>/notified/`, switch
  `AGENT_RELAY_NOTIFY=off`, preview switch `notify-preview.off`; currently for undelivered Codex messages only.

## Assumptions (accepted by the user 2026-10-09)

1. Only agents registered in the mailbox are shown or notified about; other Claude sessions on the Mac are not.
2. Claude presence comes from the registry file of the agent's recorded host session plus `liveOwner`:
   `running` (live, `idle` or `busy`), `waiting-approval` (live, `waiting` and `waitingFor` names a permission prompt),
   `waiting-input` (live, `waiting` for anything else), `stopped` (no registry file or owner gone), `unknown` (file
   unreadable or no recorded host).
3. Codex presence comes from `thread-owner-discovery`: `running` (connected owner), `stopped` (none), `unknown` (no
   socket or error). Codex `waiting-approval` is out of reach until a reliable signal is found; it shows as `running`.
   Probing it is part of the acceptance, not of this module.
4. Presence is read when `bridge_agents` runs and when a message is sent; no background polling of every session.
   The notice (D148) is the exception and checks only bound recipients of messages not yet acknowledged.
5. Interface: `presence` is an added field (minor in 1.x terms); it ships inside the 2.0 batch.

## Decisions

- **D146 presence in the directory.** `bridge_agents` adds `presence: {state, since?, detail?}` per agent with the
  states of assumptions 2–3; `since` is the registry's `statusUpdatedAt` when known. The collab skill shows it in the
  directory line (`运行中` / `已停止` / `等待授权` / `等待输入` / `未知`) and never shows pids or paths.
- **D147 send tells the sender.** `bridge_send` to an agent whose presence is `waiting-approval` or `stopped` adds a
  warning ("<name> is waiting for the user's approval in its session; your message waits"), like today's "not
  running" warning, which it replaces with the same wording rule.
- **D148 the user hears about a waiting approval.** When a message to a Claude recipient stays unacknowledged while
  that session is `waiting-approval`, the bridge shows one macOS notice on this Mac: "<name> is waiting for your
  approval" with the sender, at most once per waiting episode (key: session id + `statusUpdatedAt`), through the
  existing notice channel and its off switches. It only tells; it never approves or answers the prompt. Kept: the only
  evidence (the user's screenshot, relayed by the coordinator) shows Claude Code's "done" notice, not an approval one.
- **D149 doctor agrees with the directory.** doctor's `wake-bindings` check uses the same presence reading, so doctor
  and `bridge_agents` never disagree about a session.

## Requirements

1. Red first (bridge): presence from fixture registry files and fake processes — running (`idle`, `busy`),
   `waiting-approval`, `waiting-input`, `stopped` (no file; pid alive with another start time), `unknown` (bad JSON);
   Codex running / stopped / unknown from a fake IPC owner reply; `bridge_agents` returns `presence`.
2. Red first: `bridge_send` warns for `waiting-approval` and `stopped` recipients and not for running ones.
3. Red first (if D148 is kept): one notice per waiting episode, none when the message is acknowledged first, none
   with notices switched off, a new notice for a new episode; the notice text names the session and the sender and
   carries no approval action.
4. collab skill directory format and README updated; doctor shares the reading (D149); CHANGELOG `[Unreleased]`.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.
6. Acceptance (coordinator, after the batch): a background Claude session stuck on a permission prompt shows
   `等待授权` in the directory, the sender is warned, and (D148) the user sees one notice; a closed session shows
   `已停止`.

## Boundaries

- Always: read only; never answer a prompt, change a mode, or start, stop or resume a session.
- Ask first: reading anything beyond `~/.claude/sessions/*.json` and the Codex IPC owner reply.
- Never: show pids, full paths or internal ids in the directory; notify about sessions that are not in the mailbox.

## Success criteria

The directory tells running, stopped and waiting-for-the-user apart for Claude sessions (and running/stopped for
Codex); a sender learns at send time that its recipient is waiting or gone; the user learns, once, that a mailbox
session waits for their approval (if D148 is kept); nothing is approved on the user's behalf.

## Open questions

None. Accepted by the user on 2026-10-09 (assumptions 1–5, D146–D149; D148 kept on the evidence above, to be dropped
if the user reports that Claude Code already notifies about waiting approvals).
