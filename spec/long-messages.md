# Spec: long-messages

## Objective

Round-2 finding A3 (coordinator, 2026-10-09): a message of about 160 000 bytes sent with `bodyFile`

- (a) came back in full in `bridge_send`'s result (about 76 000 characters), filling the sender's context;
- (b) could not be read by the recipient with `bridge_inbox`: the result exceeded the host's tool-output limit, so the
  recipient fell back to `jq` on a dump file through Bash, and in default mode that stopped on a permission prompt.

Long messages are a normal part of the user's design and review work. This module makes sending one cost the sender
nothing, and makes reading one possible in pieces through the mailbox tools alone, within the host's output limit.

Readers: the user; the round-2 coordinator (acceptance after the batch).

## What exists today (main 1013731, 2026-10-09)

- `bridge/src/server.ts` `bridge_send` returns `{...message, wake, warnings?}`: the stored message including `body`.
- `bridge/src/paging.ts`: `fitMessages` keeps messages until a character budget is spent (default `DEFAULT_PAGE_CHARS
  = 48_000`, at most 400 000); the first message always returns, shortened to the budget with `bodyTruncated: true`
  and `bodyLength`. There is no way to read the rest of a shortened body. Used by `bridge_inbox` (`inboxPage`),
  `bridge_thread` (`threadPage`) and `bridge_wait`.
- The budget's comment assumes Claude Code's 25 000-token MCP output cap and about four characters per token, which
  holds for English; Chinese text runs close to one token per character, so 48 000 Chinese characters exceed the cap.
- `bridge_outbox` already shows only a 200-character preview and `body_length`.
- `bodyFile` accepts up to 256 KiB.

## Assumptions (accepted by the user 2026-10-09)

1. The sender never needs its own body back; the id, state, length and warnings are enough.
2. The page budget is counted in "cost units" that track tokens for any script: an ASCII character costs 1, any other
   character 4. The default stays 48 000 units, so English pages are unchanged and a Chinese page holds about 12 000
   characters. `maxChars` keeps its name and now means units (documented).
3. Reading the rest of a long body is a parameter of `bridge_inbox` (`messageId` with `bodyOffset`), not a new tool:
   the recipient (or, for a broadcast, any agent other than its sender) reads its own message; nobody else can.
   `bridge_thread` and `bridge_wait` point to it when they shorten a body.
4. Reading a part records the read like any inbox read; acknowledging stays a separate, explicit step.
5. Interface: the `bridge_send` result loses `body` (breaking, part of the 2.0 batch); the new parameters and fields
   are additions.

## Decisions

- **D150 the send result carries no body.** `bridge_send` returns the stored message without `body`, plus
  `bodyLength` (characters); everything else (id, thread, delivery state, wake, warnings) as today. The idempotent
  duplicate and conflict paths follow the same rule.
- **D151 budgets in token-safe units.** `fitMessages` measures bodies and envelopes in units (ASCII 1, other 4); the
  default and maximum keep their numbers; a shortened body is cut on a character boundary and never inside a
  surrogate pair.
- **D152 read a long body in parts.** `bridge_inbox` takes `messageId` and `bodyOffset` (default 0) and returns that one
  message with `body` = the part from `bodyOffset` that fits the budget, `bodyOffset`, `bodyLength` and, when more
  remains, `nextOffset`. A message not addressed to the reader is refused with the same rule as today's inbox.
- **D153 every shortened body says how to continue.** Wherever a body is shortened (inbox, thread, wait), the view
  carries `nextOffset` and the result carries one line: "Message #N is longer than this page; read the rest with
  bridge_inbox {agent, messageId: N, bodyOffset: <nextOffset>}".

## Requirements

1. Red first (bridge): `bridge_send` of a 160 000-byte `bodyFile` returns no `body`, the right `bodyLength`, and a
   result under 2 000 characters; duplicates likewise.
2. Red first: `fitMessages` with Chinese text keeps a page at most 48 000 units (about 12 000 characters) and English
   at 48 000 characters as before; a cut never splits a surrogate pair.
3. Red first: reading a 160 000-byte Chinese body part by part with `messageId` and `bodyOffset` returns every
   character exactly once and in order, each result within the default budget, the last without `nextOffset`;
   another agent's message is refused; a broadcast follows the inbox rule.
4. Red first: a shortened body in `bridge_inbox`, `bridge_thread` and `bridge_wait` carries `nextOffset` and the
   continue line.
5. collab skill: how to read a long message (no Bash); tool descriptions; README; CHANGELOG `[Unreleased]`; bridge
   records (`UPSTREAM.md`, manifest) in each bridge commit.
6. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.
7. Acceptance (coordinator, after the batch): the 160 000-byte message goes out with a short send result and is read
   in full with the mailbox tools, in default mode, without Bash and without a permission prompt.

## Boundaries

- Always: the full body stays stored unchanged; only views are shortened.
- Ask first: raising `bodyFile`'s 256 KiB limit; changing who may read a message.
- Never: write a body to a file for the reader; drop or rewrite any part of a stored body.

## Success criteria

A long message costs the sender a few hundred characters of result; the recipient reads all of it, in order, with
`bridge_inbox` alone, each piece inside the host's output limit, in any script.

## Open questions

None. Accepted by the user on 2026-10-09 (assumptions 1–5, D150–D153).
