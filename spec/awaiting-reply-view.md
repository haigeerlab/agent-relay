# Spec: awaiting-reply-view

## Objective

Only module of 0.7.0 (bridge). Item 6 of the seven-item list relayed on 2026-10-16 by a Codex monitoring session
(mailbox name `spec-guard-monitor`) with the user's consent: a "pending replies" view that lists requests sent but not
yet answered and how long each has waited, so that a session left waiting and a session that forgot to answer both
show up. The user chose it the same day ("排第 6 项：待回复视图。先写 spec，把假设列给我确认。") and accepted the eight
assumptions below ("8 条假设按你的推荐通过：加 expectsReply 标记，暂不做手动关闭，版本 0.7.0。开始写 spec。").

Users: the session that asked (is my request still open, for how long, is the other side running?), the session that
was asked (what do others wait for from me?), and an upper-layer plugin running as a Claude session that patrols the
mailbox for stuck exchanges.

## What exists today (main 1bbe48f, v0.6.11)

- `bridge_outbox` (`bridge/src/bridge-store.ts` `outbox`) lists direct messages an agent sent, newest first. By default
  it **hides messages the recipient acknowledged** (`a.acked_at IS NULL`), so a request the recipient acked and never
  answered — the "forgot to reply" case — is not in the default view. With `includeAcknowledged` it is, mixed with every
  other message.
- Replies are linked: `bridge_send.replyTo` stores `messages.reply_to` (`idempotency`, schema 4), only the original's
  recipient may reply (`identity-check`), and every outbox entry carries `replies: number[]`.
- Nothing marks a message as expecting an answer. The protocol says a woken session replies "only when complete, blocked
  or needing a decision", so an unanswered message is often correctly unanswered (a notice, an FYI); "no reply yet"
  alone cannot mean "someone is waiting".
- `bridge_agents` carries `waiting: {count, from, ids, oldestAt}` (unhandled direct messages, D198) and `presence`
  computed per agent in parallel (D146, D176), with a stability promise for 2.x. Nothing says what an agent owes.
- `session-routing` already classifies a request as `exchange: ask | assign | unknown` (D195).
- Schema 5 (`bridge/src/schema.ts`); the Python hooks accept mailbox schemas `(2, 3, 4, 5)`
  (`hooks/native_collaboration_runtime.py` `MAILBOX_SCHEMA_VERSIONS`); `interface.json` says `2.0`.
- Three stale bridge documents were deferred on 2026-10-16 to the next bridge change, because any change under `bridge/`
  alters the `UPSTREAM.sha256` mark and asks for `upgrade --confirm`: `bridge/INSTRUCTIONS.md` (says to register with
  wake "auto" by default and never to use `bridge_wait`), `bridge/CHANGELOG.md` ("agent-relay 0.5.0 (unreleased)"),
  `bridge/docs/ALTERNATIVES.md` (positions the bridge by the Codex orchestrator removed in 0.5.0).

## Assumptions (accepted by the user 2026-10-16)

1. **A sender marks a request.** `bridge_send` gains an optional `expectsReply` (boolean, default false). Only marked
   messages enter the view. Stored in a new column (schema 6, old rows false); interface 2.0 → 2.1 (an addition; Spec
   Guard accepts `>=1.0,<3.0`).
2. **A reply is a message with `replyTo` the request's id**, sent by the request's recipient. A message on the same
   thread without `replyTo` does not count. Skills tell a recipient of a marked message to answer it with `replyTo` when
   done, also when the answer is "not doing it".
3. **A request leaves the view** when it has a reply, when it failed or expired, or when its recipient is retired. There
   is no manual close for the sender (not built now; a never-answered request stays until it expires).
4. **No new tool.** The server keeps exactly ten mailbox tools (allow rules, Codex approval tables and the probe stay):
   - the asking side: `bridge_outbox` gains `awaitingReply: true`, which lists only marked, unanswered requests,
     **including acknowledged ones**, oldest first, each with the seconds waited and the recipient's presence;
   - the asked side: every `bridge_agents` row gains `owesReplies: {count, ids, oldestAt}`, the marked requests addressed
     to it that are still unanswered, with the same 2.x stability promise as `waiting`.
5. **Display only.** No new notice, no reminder, no resend. (Item 5, another notice channel, is separate.)
6. **Skills.** `collab` and `session-routing` send with `expectsReply: true` when asking a question or assigning work
   (`exchange` `ask` or `assign`); "which requests are unanswered", "who owes me a reply", "what do others wait for from
   me" read the two views.
7. **Release 0.7.0**, bridge change, `upgrade --confirm`. The three deferred bridge documents are fixed in the same
   release, so the upgrade it needs anyway covers them.
8. **Broadcasts cannot be marked**: `to: "*"` with `expectsReply: true` is refused.

## Decisions

- **D201 a request is marked by its sender.** `expectsReply` on `bridge_send`, stored as `messages.expects_reply`
  (`INTEGER NOT NULL DEFAULT 0`, schema 6). Refused on a broadcast (assumption 8). Allowed together with `replyTo`: a
  reply may itself ask a follow-up question, and then it is both an answer and a new open request. The idempotency
  comparison (`contentDifferences`) includes `expectsReply`, so a retry that changes it is refused like any other
  content change.
- **D202 answered means a linked reply from the recipient.** A request is unanswered while no message with
  `reply_to = id` exists. (Only the recipient can create one, `identity-check`.) A request is open when it is marked,
  unanswered, not `failed` or `expired`, and its recipient is not retired. Acknowledgement does not close it.
- **D203 the asking view is a filter on `bridge_outbox`.** `awaitingReply: true` returns open requests the agent sent,
  oldest first, ignoring `includeAcknowledged`. Each entry is the usual outbox entry plus `expectsReply`,
  `waitingSeconds` (whole seconds from `createdAt` to the read) and `recipientPresence` (as in `bridge_agents`, read once
  per distinct recipient, in parallel, only in this mode; a retired or hostless recipient is not looked up). Every
  normal outbox entry also carries `expectsReply`. The result adds `totalAwaitingReply` (count of open requests).
  **Cost cap (round-2 review of #117):** presence is read only for the recipients on the returned page (within
  `limit`), never for every open request counted in `totalAwaitingReply`; a Codex lookup in this view waits at most
  2 s (`codexOwner` `responseTimeoutMs`; a loaded task answers in milliseconds) and a silence reads as `unknown` with
  the detail "the ChatGPT app did not answer within 2 s", so one slow recipient cannot hold the call near the 10 s IPC
  timeout. `bridge_agents` presence keeps its 10 s behaviour (out of scope here, see Not in scope).
- **D204 the asked view is `owesReplies` on `bridge_agents`.** For every non-retired agent with open requests addressed
  to it: `{count, ids (oldest 20), oldestAt}`; absent when zero. Within 2.x its fields are only added to.
- **D205 interface 2.1, schema 6.** `interface.json` says `2.1`; the interface document lists `expectsReply`,
  `awaitingReply`, `totalAwaitingReply`, `waitingSeconds`, `recipientPresence`, `owesReplies`.
  `MAILBOX_SCHEMA_VERSIONS` becomes `(2, 3, 4, 5, 6)`; the rollback caveat names schema 6. A 0.6.x bridge still running
  beside a migrated mailbox opens it in its compatible mode and stores its sends with the column default (not marked).
- **D206 skills mark and read.** `collab` and `session-routing`: mark questions and work requests **sent through the
  mailbox**; a request delivered natively (Claude `SendMessage`, a Codex thread turn, including a same-turn Codex →
  Codex `ask` routed natively by D195) is never marked, because a native answer creates no `replyTo` (round-2 review of
  #117). Tell the recipient of a marked message to answer with `replyTo` when done; route the questions in assumption 6
  to the views. The MCP server instructions add one sentence: answer a message marked `expectsReply` with `replyTo`
  when done.
- **D207 the deferred bridge documents ride along.** `INSTRUCTIONS.md` rewritten to the current rules (wake null by
  default, `bridge_wait` allowed for unbound agents in an active turn, mark requests), `bridge/CHANGELOG.md` entry
  "agent-relay 0.5.0" without "(unreleased)" plus a 0.7.0 line, `docs/ALTERNATIVES.md` deleted with its link in
  `bridge/README.md`; `UPSTREAM.md` row and manifest (D24) in the same commit.

- **D208 upgrade order: plugins first, then the runtime** (round-2 review of #117). The 0.6.11 hooks accept mailbox
  schemas 2–5 only and are already shipped: on schema 6 their doctor says to update the plugin, but `retire` stops with
  a bare "unsupported native mailbox schema" and the delegation backend silently finds no result route. So the
  CHANGELOG "upgrading from 0.6.11" and the README say: update the plugin on **both** hosts to 0.7.0 (new sessions,
  ChatGPT restarted) before `upgrade --confirm`. From 0.7.0 on, every hook that meets a schema newer than it knows
  says so with the next step "update the agent-relay plugin" (doctor already does; `retire` and the delegation backend
  get the same wording), so the next schema bump is not silent.

## Requirements

1. Red first, `bridge/test/`: schema 6 migration adds `expects_reply` with old rows false, from 5 and from an empty
   database; a schema-6 database opened by a build that knows 5 reports `newer`.
2. Red first: `bridge_send` stores `expectsReply`; a broadcast with it is refused with a clear message; a retry with the
   same key and a different `expectsReply` is refused (D201).
3. Red first: `outbox(..., { awaitingReply: true })` lists a marked request until a linked reply arrives — also after the
   recipient acked it — and drops it on reply, `failed`, `expired`, or retirement of the recipient; unmarked messages
   never appear; order is oldest first; `waitingSeconds` uses an injected clock; `totalAwaitingReply` counts all open
   ones beyond `limit`.
4. Red first: `bridge_outbox` with `awaitingReply` reads presence once per distinct recipient on the returned page (a
   counting fake), not for recipients beyond `limit` and not for a retired one; without `awaitingReply` it reads none;
   a Codex recipient whose socket never answers costs at most about 2 s and reads `unknown` with the 2 s detail.
5. Red first: `bridge_agents` gives `owesReplies` only for agents with open requests, ids oldest first (at most 20),
   `oldestAt` of the oldest; a reply or expiry removes it.
6. Python: `MAILBOX_SCHEMA_VERSIONS` includes 6; doctor, retire and the delegation backend read a schema-6 mailbox
   (tests with a fixture); on a schema newer than they know, `retire` and the delegation backend report "update the
   agent-relay plugin" (D208); rollback caveat text.
7. Skills and docs: `collab`, `session-routing` (D206), server instructions, `docs/collaboration-interface.md` (D205),
   README and `README.en.md` (how to ask "who owes me a reply"), CHANGELOG with "bridge changed, `upgrade --confirm`",
   the bridge documents (D207), `UPSTREAM.md` and manifest (D24); `interface.json` 2.1.
8. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; CI green.

## Boundaries

- Always: keep the ten-tool surface; keep reading presence parallel and only in the awaiting-reply mode.
- Ask first: any notice, reminder or automatic resend for an open request; a manual close.
- Never: infer "expects a reply" from message text; treat an acknowledgement as an answer; read message bodies to
  build either view (ids, times and counts only).

## Success criteria

- A Claude session asks a Codex session a question with `expectsReply`; the Codex session acks without answering: the
  asker's `bridge_outbox` with `awaitingReply` lists it with a growing `waitingSeconds` and the recipient's presence, and
  `bridge_agents` shows `owesReplies` on the Codex identity. The Codex session answers with `replyTo`: both views drop it.
- An unmarked message never appears in either view.
- After `upgrade --confirm`, existing messages are unmarked and nothing else changes; a 0.6.11 bridge still running
  against the migrated mailbox keeps working.

## Acceptance (coordinator, after 0.7.0)

- The success criteria on the real host, both directions (Claude asks Codex, Codex asks Claude).
- "谁欠我回复" and "别人在等我回复什么" asked in natural language give the two views.
- doctor ok on schema 6; `bridge/INSTRUCTIONS.md` matches the server instructions.

## Not in scope and known limits

- Notices, reminders, automatic resends and a manual close for open requests.
- During the transition a recipient still running a 0.6.x bridge does not see the server sentence about answering
  with `replyTo` and may handle a marked request without replying; that request stays open until it expires (round-2
  review of #117). CHANGELOG states it.
- `bridge_agents` presence can take up to the 10 s IPC timeout per unloaded Codex task (observed by the round-2
  coordinator 2026-10-16); a cap there is a separate item.

## Open questions

None.
