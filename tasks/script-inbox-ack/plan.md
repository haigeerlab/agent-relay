# Plan: script-inbox-ack

<!-- spec-guard: review approved -->

Based on [`spec/script-inbox-ack.md`](../../spec/script-inbox-ack.md) (approved by the user on 2026-11-20: assumptions
1–11, D271–D275). Built on branch `claude/script-inbox-ack-df1d09` from main 439a6f2; one PR. ecosystem-lead has no
objection to interface 2.11 (mailbox #21649, relayed by the owner session), so there is no interface gate. Nothing here
touches the main clone, the hosts, the runtime or the mailbox on this Mac.

Found while planning (read-only, 2026-11-20, main 439a6f2):
- `bridge_inbox`'s handler body (`src/server.ts:378-415`) uses only `store`, `ownRead`, `readReceipt`, `afterRead` and
  `continueLines`; none needs the MCP server, so it can move to a function that takes `store` and `recorded`.
- `continueLines` (`src/paging.ts:70`) hard-codes the `bridge_inbox {…}` wording; it gains an optional formatter.
- `send`'s script check (`src/cli-main.ts:168-172`) is the one to share with `inbox` and `ack` (D273).
- `store.ack` already acknowledges broadcasts delivered to the agent (`DELIVERED_TO`, `src/bridge-store.ts:252`), and
  `countUnread` counts them; no store change is needed.
- `hooks/test_packaging.py:40` pins `interface.json` (2.10, the `script` block); `hooks/relay_status.py:5` lists the
  interface history; `skills/collaboration-ops/SKILL.md:130-147` describes script identities and retirement.

## Task List

### Task 1: shared inbox read (D271, requirement 3)
Move the body of `bridge_inbox` into `src/inbox-read.ts` `readInbox(store, params, {recorded, continueLine?})`, with the
receipt and `afterRead` logic; `continueLines` takes an optional line formatter (default: today's `bridge_inbox`
wording). `bridge_inbox` calls it with `ownRead(agent)`. Pure refactor: no test changes; verification is the existing
`read-receipt`, `long-messages`, `read-own-sent`, `mailbox-polish` and `mcp-integration` tests staying green.

### Task 2: parse `inbox` and `ack` (D271, D272)
Red first in `cli.test.ts`: `inbox <name>` with every option in kebab case maps to `bridge_inbox`'s fields; `ack <name>
--ids 3,4` gives `[3, 4]`; usage errors for a missing name, missing `--ids`, bad ids, `--limit 0`/`201`, `--max-chars
999`, `--max-body-chars -1`, `--body-offset` without `--message-id`, an unknown option. Green: `CLI_COMMANDS` gains
`inbox` and `ack`, `ParsedCliCommand` gains `inbox` and `ackIds`, ranges as the MCP schema. Help text lists both.

### Task 3: run `inbox` and `ack` as a script identity (D271–D273, requirement 1)
Red first in `script-cli.test.ts` (child-process CLI against a test mailbox):
(a) `inbox` of a script identity that received a direct message and a broadcast lists both, field for field as
`readInbox` gives them, with `readRecorded: true`; afterwards the direct message has `read_at` and is `accepted`;
(b) a long body: a page carries a `continue` line naming `agent-relay inbox <name> --message-id … --body-offset …`, and
running it returns the next part;
(c) `ack --ids <both>` returns `{acknowledged: 2, remainingUnread: 0}`; `countUnread` is 0, so retirement no longer
blocks (the same rule `native_collaboration_retire.py` uses, D59);
(d) `inbox` / `ack` with a session identity exit 1 with D273's sentence and change nothing; unknown and retired names
exit 1; `send` keeps its refusal (now from the shared check);
(e) `bridge_ack` for a script identity is still refused (existing `script-access` test kept, its message updated in
Task 4).
Green: `cli-main.ts` gets `inbox` (writable store, `readInbox` with `recorded: true` and the CLI continue line) and
`ack` (`store.ack`, `touch`, `countUnread`), and one `requireScriptIdentity(store, name)` used by `send`, `inbox`, `ack`.

### Task 4: wording (D274, requirement 2)
Red first: the `addressing` / `script-access` test expects D251's new warning ("…its script reads this when it next
runs agent-relay inbox; until then it stays queued and may expire"); the `identity` test expects the script refusal to
name `agent-relay send, inbox and ack`; the `script-cli` test expects the register preview and the `sessions` note to
say the same. Green: the four strings.

### Task 5: interface 2.11 and docs (D275, requirements 4–5)
Red first: `test_packaging.py` expects `"interface": "2.11"` and `inbox` / `ack` argv in the `script` block. Green:
`interface.json`; `relay_status.py` docstring (2.11 since script-inbox-ack D275); `docs/collaboration-interface.md` §1
version line, §2.4 table rows, Read-only, Script identity, Wake limits, and the `bridge_send` row's D251 note;
README / README.en: remove the known issue, script section examples for `inbox` / `ack` and drop the
`--expects-reply` caution, retire paragraph (an expired direct message does not count, a broadcast never expires and
must be acknowledged, a script identity acknowledges with the CLI), glossary row, interface number;
`skills/collaboration-ops/SKILL.md` script and retire lines; CHANGELOG `[Unreleased]` and `bridge/CHANGELOG.md`
(interface 2.11, runtime upgrade needed); `bridge/UPSTREAM.md` rows; `python3 scripts/bridge-manifest.py`.

### Checkpoint (report): bridge green
`npm run check` in `bridge/` and `bash scripts/validate.sh` green; results recorded in the todo.

### Checkpoint (gate): PR review and merge
Open the PR (Chinese title and description, no consumer names). Review via the five-axis review; CI green. The user
approves and merges. No release, no version bump, no change on this Mac; then the result goes to the owner session
(PR link, command usage, interface 2.11, README and interface document changes).

## Risks

- Task 1 moves live MCP code; the existing inbox tests are the guard, and the refactor lands as its own commit.
- `inbox` opens the mailbox writable while bridge processes run; it uses the same `BridgeStore` open, busy timeout and
  transactions as `send`, so no new locking.
- The CLI continue line must not leak into `bridge_inbox`: Task 3 (b) checks the CLI wording, the existing long-message
  tests check the MCP wording.
