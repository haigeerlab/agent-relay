# Spec: ops-commands

## Objective

Give operators and agents the everyday checks the mailbox lacks: one `doctor` that says whether this Mac's
agent-relay is healthy and what to do next; `whoami` for a session's own identity; the status of one sent message and
a wait on its outcome; a message body read from a file so it arrives byte-identical; and one documented time format
for the delegation `--expires-at`. Interface gaps h, i; §2.1 rows 45, 51, 53; §2.3 rows 65, 69; §4 row 91; §10 rows
161, 165; baseline findings 2 and 6 (interface §14, `[BL §Findings]` numbering — not the round 1 report's
numbering, where finding 2 is the migration order and finding 6 the Codex approval subtables of `safe-uninstall`);
checklist A1, A5, D2, C8, D16.

Readers: the user; the round 1 coordinator (round 2 uses `doctor` in A1 and `whoami` in A5/D2); agents building
`safe-uninstall`.

## What exists today (measured, main 114ea60, 2026-10-07)

- **Tool surface is pinned by host entries:** Codex gets `enabled_tools` = the ten `MAILBOX_TOOLS`
  (`native_collaboration_runtime.py:234-238`, written by `codex_fragment`), Claude gets deny rules for the seven
  `DENIED_TOOLS`; delegated sessions are limited to the same ten. A new MCP tool would need every installed Codex
  entry rewritten (a host config change) and the delegation allow lists changed.
- **Status by id:** `bridge_wake_status` takes only `agent?` and lists recent wake jobs; `bridge_outbox` lists a
  sender's messages. There is no lookup of one message. `bridge_wait` waits for new *inbox* messages only.
- **Identity:** `bridge_sessions` returns live Claude sessions and `thisSession`; since `identity-check` the process
  knows the names it proved and agents carry `host`. Nothing answers "which names are mine, what host, what project".
  Claude's session registry (`~/.claude/sessions/<pid>.json`) has `name` (the session title), `cwd` and `status`
  (`idle`, `busy`, `waiting` seen on this Mac).
- **Body:** `bridge_send.body` is a string only. Agents that build a body in a shell risk quoting changes (D16).
- **doctor:** the bridge's own `cli doctor` checks upstream's install layout, not agent-relay's. agent-relay has
  `native_collaboration_runtime.py status | probe | install | upgrade`; host entries are only written, never checked
  (Claude's user-scoped MCP entry lives in `~/.claude.json` `mcpServers`, deny rules in `~/.claude/settings.json`;
  Codex in `~/.codex/config.toml`).
- **Background prompts (baseline finding 6, interface §4 row 91):** the delegation controller already launches Claude targets only in `dontAsk` (or
  `plan` for a host-native plan session) (`session_delegation_claude.py:193-207`), so a delegated target cannot hang on
  a prompt; any other wake-bound Claude session can still sit `waiting` and its pings go unanswered. Nothing reports it.
- **`--expires-at` (checklist C8; baseline finding 2):** `type=int` epoch seconds (`session_delegation_control.py:673`); an ISO string exits 2
  with argparse's message; not documented in the skill.

## Assumptions

Confirmed by the user on 2026-10-07, including one read-only `doctor` run against the real `~/.agent-relay` and
host files during the live check.

1. **No new MCP tools** (D41): every agent-facing command extends one of the ten existing tools, so installed host
   entries and delegation allow lists stay valid and no host config changes.
2. **`doctor` is read-only** and a command of `native_collaboration_runtime.py`: it never writes host config, the
   mailbox or the runtime, never starts sessions, and only reads `~/.codex/config.toml`, `~/.claude.json`,
   `~/.claude/settings.json` and `~/.claude/sessions/`. It reports each check as `ok`, `warn` or `fail` with one next
   step; the exit code is 1 only when something is `fail`.
3. **whoami answers for the calling session** and so lives in the bridge (only the bridge process knows its caller):
   `bridge_sessions` gains `whoami` — the verified host (Claude) or `unknown` (Codex), session title and project
   (Claude registry `name`, `cwd` basename; Codex: unknown), and each identity this session may act as (proven here or
   recorded for it) with its wake binding and recorded host.
4. **Status and wait by id are for messages the caller sent** (or received): `bridge_wake_status` gains `messageId`;
   `bridge_wait` gains `messageId`, and then waits for that message's outcome instead of new inbox messages and
   acknowledges nothing.
5. `relay_status.py` output and `ready` rule unchanged; `interface.json` stays 1.0; no schema change.

## Decisions

D41–D45 accepted on 2026-10-07 (256 KiB cap; ISO 8601 with offset documented, epoch seconds still accepted).

- **D41 extend, don't add:** whoami → `bridge_sessions.whoami`; status → `bridge_wake_status({messageId})`; wait →
  `bridge_wait({agent, messageId})`; file body → `bridge_send({bodyFile})`. Alternative: new tools plus a host-entry
  rewrite in round 2.
- **D42 doctor checks:** runtime `status` (ready, bridge current); `probe`; mailbox (schema accepted, `quick_check`,
  owner-only mode, size, undelivered backlog per recipient against the cap); host entries (Codex table present and
  pointing at this runtime with exactly the ten tools; Claude `mcpServers.agent-relay` pointing at this runtime and the
  seven deny rules present); Codex auto-approval (guardian/never → `warn`: Codex wake refused, same rules as the
  bridge); wake-bound Claude identities whose session is `waiting` → `warn` "live but blocked on a prompt; pings will
  not be handled" (a new check for interface §4 row 91), or not running → `warn` "binding to a closed session"; old Spec Guard bridge servers
  still running → `warn`. Codex thread liveness is not observable → reported `unknown`, not a warning.
- **D43 body from file:** `bodyFile` is an absolute path to a regular file (not a symlink) owned by the user, at most
  256 KiB, valid UTF-8; exactly one of `body` and `bodyFile`; the stored body is the file's text unchanged (CRLF,
  trailing newline, shell metacharacters). Alternative caps: 64 KiB, 1 MiB.
- **D44 `--expires-at` format:** ISO 8601 with an explicit offset (`2026-10-08T18:00:00+08:00` or `…Z`) is the
  documented format; integer epoch seconds stay accepted for existing callers; a time without an offset, or anything
  else, exits 2 with a message naming the format. Alternative: epoch seconds only, documented.
- **D45 wait-by-id outcome:** `bridge_wait({messageId})` returns when the message is acknowledged, replied to, or ends
  `failed` or `expired` (`unknown` keeps waiting, since evidence may still arrive), or at the timeout, with the same
  status object as `bridge_wake_status({messageId})`. Only the message's sender or recipient may ask.

## Requirements

1. `bridge_sessions.whoami` per assumption 3, tested for a Claude and a Codex (no session env) bridge.
2. `bridge_wake_status({messageId})` and `bridge_wait({messageId})` per D45, tested for each outcome, timeout, and a
   caller who is neither sender nor recipient (refused).
3. `bridge_send({bodyFile})` per D43, tested: byte-identical with metacharacters, CRLF and no trailing newline;
   symlink, other owner (where testable), too large, non-UTF-8, relative path, both or neither field refused.
4. `doctor` per D42 with fixtures for every check and both exit codes; read-only (file mtimes unchanged in tests).
5. `--expires-at` per D44, tested; the session-delegation skill documents it.
6. Docs: README (doctor, whoami, status/wait by id, bodyFile), collab and collaboration-ops skills, interface rows,
   checklist A1, A5, C8, D2, D16, `UPSTREAM.md` / `UPSTREAM.sha256`.

## Testing strategy

TS tests in the bridge (MCP-level with the `test/support/session.ts` helper); Python tests for `doctor` and
`--expires-at` with fixture homes. Live (temporary `AGENT_RELAY_HOME`, coordinator told first): `doctor` on a
temporary runtime (and, read-only, the real host entries only if the user agrees), whoami from a Claude and a Codex
bridge, D16 with a metacharacter file, wait-by-id until a reply. No host config change.

## Boundaries

- Always: read only in `doctor`; keep the ten-tool surface.
- Ask first: adding a tool. (One read-only `doctor` run against the real `~/.agent-relay` and host files is
  approved for the live check.)
- Never: write host config, start sessions from `doctor`, push without approval.

## Success criteria

1. All tests green.
2. Live checks pass; A1/A5/D2/C8/D16 targets met.
3. Docs updated.

## Open questions

None.
