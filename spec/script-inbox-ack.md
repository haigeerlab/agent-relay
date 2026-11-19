# Spec: script-inbox-ack

<!-- spec-guard: review approved 5830cfd4f5cf -->

## Objective

Local ledger item 99V3EDK, found in the 0.9.3 acceptance (2026-10-27): a script identity can send but cannot read or
acknowledge what is sent to it. Reproduced: register a script identity, send it a message, `bridge_ack` on its behalf
is refused (only the CLI acts as a script identity), the CLI has no `inbox` or `ack`, and retiring the identity is
refused for the unacknowledged message. A direct message expires after its timeout (default 24 h); a broadcast never
expires, so a script identity that has received a broadcast can never be retired (seen on the real host on
2026-11-20: two test script identities hold 8 and 7 unacknowledged messages, 7 of them broadcasts). D251's warning
("an answer comes only when its script next runs") also promises something the CLI cannot do.

This module adds the missing half: `inbox` and `ack` in the runtime CLI, acting only as a script identity. Requested by
the user in the owner session ("先做 99V3EDK"); assumptions confirmed by the user in this session on 2026-11-20.
ecosystem-lead raised no objection to the interface change (mailbox #21649) and asked for two points that this Spec
carries: the CLI `ack` refuses a session identity with a clear hint (D273), and the result sent to the owner names
the new commands and the interface version (Acceptance).

Readers: the user; the owner session (review, release, acceptance); ecosystem-lead (interface 2.11).

## What exists today (main 439a6f2, v0.9.5, interface 2.10, schema 7)

- `bridge/src/cli-logic.ts` `CLI_COMMANDS`: `retire`, `help`, `version`, `agents`, `outbox`, `sessions`, `send`,
  `register-script-identity`. `send` already takes `--reply-to`, `--expects-reply`, `--also-answers`, `--withdraws`,
  so a script can already answer a request addressed to it — once it can read it.
- `bridge/src/cli-main.ts`: the three reads open the mailbox `readOnly`; `send` and `register-script-identity` open it
  writable. `send` refuses a `--from` that is not a live script identity (D244).
- `bridge_inbox` (`server.ts`) pages the inbox (`store.inboxPage`) or one message part (`store.messagePart`, D152).
  Only the identity itself records the read (`ownRead`, D99/D100): `wakes.recordRead` sets `read_at` and moves the
  delivery state to `accepted`, and `touch` records activity. `continueLines` (`paging.ts`) tells how to read the rest of
  a long body, worded for `bridge_inbox`.
- `bridge_ack` calls `caller.require` (D37), which refuses every script identity (`identity.ts` `owns`, D244), then
  `store.ack`. `store.ack` acknowledges only messages delivered to the agent: a direct message addressed to it, or a
  broadcast it did not send created after it registered (`DELIVERED_TO`); it also sets `read_at` (D197) and closes the
  wake job (D130).
- `native_collaboration_retire.py` refuses while a delivered message is unacknowledged and not `expired`. A broadcast
  has no delivery state and no expiry, so it blocks until acknowledged. README's retire paragraph says "已过期的不算"
  and offers "等这些消息过期", which never happens for a broadcast.
- D251 (`addressing.ts`): a send to a script identity warns "nothing wakes it or prompts it to read this. An answer, if
  any, comes only when its script next runs." Interface §2.4 says replies to a script identity "are read with `outbox` /
  `agents`", which show no bodies. README "已知问题" lists the gap (L314–316) and tells scripts not to use
  `--expects-reply`.

## Assumptions (confirmed by the user, 2026-11-20)

1. **One module**, id `script-inbox-ack`, after `delivery-robustness`; it changes runtime files, so its release needs
   `upgrade --confirm`. The bridge version is set at release (D252), not here.
2. **`inbox <script identity>`** prints `bridge_inbox`'s result, field for field, from the same code (the handler's body
   moves into a shared function that the MCP tool and the CLI call). Options are `bridge_inbox`'s fields in kebab case:
   `--from-agent`, `--thread`, `--after-id`, `--include-acknowledged`, `--include-expired`, `--limit`, `--max-chars`,
   `--max-body-chars`, and `--message-id N [--body-offset M]` for one message part. Broadcasts delivered to the
   identity are listed as in `bridge_inbox`. `continue` lines name the CLI command, not `bridge_inbox`.
3. **The CLI's read is the identity's own read.** `inbox` records the read (`read_at`, delivery `accepted`, wake job
   `read`) and activity, and returns `readRecorded: true`. It therefore opens the mailbox writable, unlike the other
   three reads; a message that is read stops counting toward expiry like any accepted message.
4. **`ack <script identity> --ids 12,15`** prints `bridge_ack`'s result `{acknowledged, remainingUnread}` through
   `store.ack`, so it acknowledges direct messages and broadcasts delivered to the identity, and nothing else.
5. **Script identities only.** `inbox` and `ack` act only as a registered, not retired identity whose recorded host is
   `script`. A session identity is refused with a hint that only its own session reads it as itself and acknowledges it
   (`bridge_inbox`, `bridge_ack`); an unknown or retired name is refused as `send` refuses it. D37 is unchanged:
   `bridge_ack` still refuses to act for a script identity, and no session check is loosened. The CLI offers no
   bystander read of a session's inbox (MCP still does).
6. **`send` is unchanged**; README stops telling scripts to avoid `--expects-reply`.
7. **D251 reworded**: the warning says nothing wakes a script identity, its script reads the message the next time it
   runs `agent-relay inbox`, and until then it stays `queued` and may expire. §2.4's "Wake limits" says replies are
   read with `inbox`.
8. **Interface 2.10 → 2.11**; `interface.json`'s `script` block gains `inbox` and `ack`. Mailbox schema 7 unchanged.
9. **Docs**: README (and `README.en.md`): the "已知问题" entry is removed; the script section gains `inbox` / `ack`
   examples; the glossary's "只能发不能确认" changes; the retire paragraph is corrected: an expired direct message does
   not count, a broadcast never expires and must be acknowledged, and a script identity is acknowledged with the CLI.
   Interface document §1 version line and §2.4 (command table, Read-only, Script identity, Wake limits). CHANGELOG
   `[Unreleased]`.
10. **Out of scope**: a long poll for scripts (no `bridge_wait` equivalent); `native_collaboration_retire.py` (that a
    broadcast must be acknowledged is intended, and a script identity can now do it); the schema; any session check.
11. **Acceptance samples**: after release and upgrade, the owner session acknowledges the messages of the two test
    script identities on the real host with the new CLI and then retires them. This session does not touch them.

## Decisions

- **D271 CLI `inbox`.** Assumptions 2 and 3. Output and paging are `bridge_inbox`'s, from one shared function; the CLI
  passes `recorded: true` and a continue-line wording
  `read the rest with agent-relay inbox <agent> --message-id <id> --body-offset <offset>`. Reading back a message the
  identity sent records nothing (D212, inherited). Option values are checked as the MCP schema checks them
  (`--limit` 1–200, `--max-chars` 1000–400000, `--max-body-chars` 0–400000, ids positive integers, `--body-offset`
  only with `--message-id`); a bad value is a usage error (exit 2).
- **D272 CLI `ack`.** Assumption 4. `--ids` is required and takes ids separated by commas (as `--also-answers`); the
  activity is recorded as `bridge_ack` records it.
- **D273 the CLI acts only as a script identity.** Assumption 5. One check for `send`, `inbox` and `ack`. Wording:
  - session identity: `"<name>" is a session identity: only its own session reads its inbox as itself and
    acknowledges its messages (bridge_inbox, bridge_ack). The agent-relay CLI acts only as a script identity.`
  - unknown or retired: the existing `send` refusal (`"<name>" is not a script identity; register one with
    register-script-identity <name> --confirm.`), retired names saying they were retired.
- **D274 wording follows the new commands.** D251's warning (assumption 7); `identity.ts`'s refusal for a script
  identity and `register-script-identity`'s preview name `send`, `inbox` and `ack` instead of `send` alone; the
  `sessions` note says a script acts only as a script identity. Warnings and notes are free text, not interface.
- **D275 interface 2.11.** Judged by interface §1: two commands are added and nothing is removed, renamed or narrowed,
  so the change is minor. `inbox` is not a read-only command (§2.4 says which are). Schema 7 unchanged.

## Requirements

1. Red first (`script-cli.test.ts` or a new `script-inbox.test.ts`, running the built CLI against a test mailbox):
   - `inbox` of a script identity lists a direct message and a broadcast sent to it, equals `bridge_inbox`'s fields,
     returns `readRecorded: true`, and afterwards the direct message is `accepted` with `read_at` set;
   - `--message-id` with `--body-offset` returns the next part of a long body; a page with a shortened body carries a
     `continue` line naming `agent-relay inbox`;
   - `ack` of a direct message and a broadcast returns `{acknowledged: 2, remainingUnread: 0}`, and the identity can
     then be retired by `native_collaboration_retire.py` (or the equivalent unread check);
   - `inbox` and `ack` with a session identity exit 1 with D273's sentence; with an unknown or retired name exit 1;
     a missing name, missing `--ids`, bad ids or out-of-range options exit 2;
   - `bridge_ack` for a script identity is still refused (existing test kept).
2. Red first (`addressing` test): the D251 warning has the new wording.
3. Existing `bridge_inbox` tests stay green unchanged (the shared function changes no MCP output).
4. `interface.json` 2.11 with `inbox` and `ack` argv; any test that lists the `script` block updated; `UPSTREAM.md`
   rows for changed bridge files; `python3 scripts/bridge-manifest.py`.
5. Docs as in assumption 9; skills or references that say a script identity cannot read or acknowledge are corrected.
6. `bash scripts/validate.sh` green; CI green.

## Boundaries

- Ask first: anything on this Mac's runtime, hosts or mailbox (none planned).
- Never: touch the two test script identities on the real host; loosen D37 or any session-side check; change the
  schema; bump the bridge version or release.

## Acceptance (owner session, after release and upgrade)

- `~/.agent-relay/bin/agent-relay inbox <test script identity>` lists its unacknowledged messages, broadcasts included,
  with `readRecorded: true`.
- `~/.agent-relay/bin/agent-relay ack <test script identity> --ids <those ids>` returns `remainingUnread: 0`, and
  `native_collaboration_retire.py --name <test script identity> --confirm-retire` then succeeds.
- `ack` with a session identity's name is refused with D273's hint.
- The result to the owner session names the new commands (`inbox`, `ack` and their options) and interface 2.11, for
  the release notice.

## Open questions

None.
