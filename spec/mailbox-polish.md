# Spec: mailbox-polish

## Objective

Three small round-2 findings (coordinator, 2026-10-09):

- **A5.** After an offline message was delivered (the session came back, was woken and replied), its `deliveryState`
  in the inbox still read `unknown`.
- **A6.** On first use a Claude session asks the user to approve each of the ten `bridge_*` tools; nothing tells the user
  how to approve them once.
- **A7.** The session-routing skill tells the agent to pass JSON to the selector with a heredoc; in Codex's read-only
  sandbox a heredoc cannot create its temporary file and fails, so Codex fell back to `printf` by itself.

Also, from the coordinator's list: Claude Code's project-trust dialog preselects "No, exit"; the user twice refused it
by accident. That dialog is Claude Code's, not agent-relay's; the docs mention it.

Readers: the user; the round-2 coordinator (acceptance after the batch).

## What exists today (main 7e29b8a, 2026-10-09)

- `bridge/src/delivery.ts`: `unknown` may move only to `accepted`, on evidence: a late host receipt or the recipient
  fetching the message. `wake-queue.ts` `recordRead` marks the message read (and its delivery `accepted`) when the
  recipient's own inbox read is recorded; `acknowledge` does the same. A read is not recorded when the name was not
  proven by this session (for example after a bridge restart, before it registers again: `readRecorded: false`).
- `bridge_inbox` builds its page **before** `recordRead` runs, so the page shows the state from before this very read.
- A reply (`bridge_send` with `replyTo` from the original's recipient, identity-check D-rule) is not counted as evidence.
- Claude tool rules: `session_delegation_claude.py` `communication_rules(server_name, tools)` already builds exact
  `mcp__<server>__<tool>` rules; the Claude server name is `agent-relay` (`native_collaboration_adapters.py:26`).
  Claude Code's documented best practice is exact tool names rather than a wildcard. Codex already pre-approves the
  mailbox tools (codex-gated-wake D70).
- `skills/session-routing/SKILL.md:19-24`: "JSON 用 heredoc 或管道从 stdin 传入".

## Assumptions (accepted by the user 2026-10-09)

1. A5 has two causes, both fixed and both covered by tests that reproduce them first: the inbox page shows the state
   from before the read it records, and a reply from the recipient is not taken as evidence of delivery.
2. A reply is evidence only when it comes from the original message's recipient and names it in `replyTo`
   (the same rule that lets it reply at all).
3. A6 is guidance only: agent-relay prints the exact lines and where they go; it never writes `~/.claude/settings.json`.
   The rules are the exact tool names, not a wildcard.
4. A7 is wording only: the skill shows a pipe (`printf '%s' '<json>' | python3 -B …`), which works in Codex's
   read-only sandbox and in Claude Code.
5. Interface: no tool, field or state changes; a new read-only adapters subcommand.

## Decisions

- **D154 the inbox shows the state after its own read.** `bridge_inbox` (list and part reads) and `bridge_wait` return
  each message's `deliveryState` as it is after `recordRead` ran in the same call.
- **D155 a reply is evidence of delivery.** When the original's recipient sends a reply (`replyTo`), an `unknown` (or
  still `queued`/`sending`) original moves to `accepted`, as a fetch would, and its open wake job closes as `read`.
- **D156 one-time approval lines for Claude.** `native_collaboration_adapters.py claude-allow-rules` (read only)
  prints the ten exact rules and the `permissions.allow` snippet for `~/.claude/settings.json`. The collab skill, on a
  Claude session's first join, tells the user these lines exist and how to see them, and that adding them is the
  user's choice. README states the same and mentions Claude Code's trust dialog preselecting "No, exit".
- **D157 the selector input is piped.** session-routing shows `printf '%s' '<json>' | python3 -B …/session_routing.py
  select` and no longer suggests a heredoc.

## Requirements

1. Red first (bridge): a message whose wake ended `unknown` reads `accepted` in the very inbox call that fetches it;
   in `bridge_wait` too.
2. Red first: an `unknown` message becomes `accepted` when its recipient replies with `replyTo`, not when anyone else
   sends a message with that `replyTo` (refused anyway) and not for a broadcast original.
3. Red first (Python): `claude-allow-rules` prints exactly the ten `mcp__agent-relay__bridge_*` rules once each and a
   JSON snippet that parses; it writes nothing.
4. Skills (collab: first-join note; session-routing: pipe), README, CHANGELOG `[Unreleased]`; bridge records in the same
   commit as the bridge change.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.
6. Acceptance (coordinator, after the batch): an offline message, delivered after the session returns and replied to,
   shows `accepted`; session-routing in a Codex read-only task passes its JSON without a sandbox failure.

## Boundaries

- Always: evidence only moves `unknown` forward to `accepted`; nothing is ever replayed.
- Ask first: writing any host settings file.
- Never: a wildcard rule in our guidance; marking a message delivered without the recipient's own action.

## Success criteria

A delivered and answered message never reads `unknown`; a new Claude user can approve the mailbox tools once with lines
agent-relay prints; the routing skill works as written in a Codex read-only sandbox.

## Open questions

None. Accepted by the user on 2026-10-09 (assumptions 1–5, D154–D157).
