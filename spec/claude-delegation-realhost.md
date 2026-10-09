# Spec: claude-delegation-realhost

## Objective

First module of 0.6.2. The round-2 coordinator's real-host acceptance of 0.6.1 (2026-10-10; the user: "按你的推荐，四点都
同意") passed every mailbox item and found two high problems in Codex → Claude Code delegation, both invisible to the
fixtures 0.6.1 was tested with:

- **H1.** A stopped Claude delegation is never resumed: the follow-up returns `held/target-status-unknown`, so the
  0.6.1 fix (#64, continue repeats the launch limits) is unreachable on a real host.
- **H2.** Sometimes the delegated session never gets its mailbox tools: it cannot register, cannot report back, the
  record ends `unknown`, and `continue` then refuses with no way forward.

Plus L1: `prune --help` still says "--confirm cancels them".

Readers: the user; the round-2 coordinator (acceptance after 0.6.2).

## What exists today (main d18a5ef, v0.6.1)

- **H1.** Claude Code 2.1.295 reports a stopped background session in `claude agents --json --all` as
  `"state": "done"` with no `status` and no `pid` (the coordinator, 2026-10-10, session `cx2cc-readme2`). The entry parser
  accepts `done` (`session_delegation_claude.py:547`), but `_deliver` resumes only
  `session.state in ("stopped", "exited", "failed")` (`:852`) and otherwise holds with `target-status-unknown`. The 0.6.1
  real check ran `claude -p --resume` directly, not through the adapter, and the adapter tests used `"stopped"`.
- **H2.** On the failing run (session 6472d974) the first turn's attachment was `deferred_tools_delta` with
  `pendingMcpServers: ["agent-relay"]` and `toolSearchAbsent: true`; the session answered that the mailbox tools were not
  connected and no ToolSearch was available. `_bounded_prompt` tells it to wait and load them "by name with ToolSearch"
  (`:292`), but the launch's `--tools` list (`_permission_shape`) has no `ToolSearch`. The same request succeeded on the
  second try within 50 s; the MCP server itself lists its tools when started by hand.
- After H2 the record is `unknown`; `continue` raises `delegation-is-not-ready-for-follow-up`; `cancel` of an `unknown`
  Claude record with a host id stops the host (existing path), but nothing tells the user that cancel-then-create is the
  next step.

## Assumptions (accepted by the user 2026-10-10)

1. **H1.** A Claude session whose agents entry says `done` (no `pid`) is resumable exactly like `stopped`, `exited`,
   `failed`; the resume uses the 0.6.1 launch limits. A fixture taken verbatim from Claude Code 2.1.295's
   `agents --json --all` output after `claude stop` pins it.
2. **H2.** `ToolSearch` joins the launch tool list of every Claude delegation (both intents, with and without user
   environment). It only loads tool schemas that the launch's MCP configuration (`--strict-mcp-config`) and `--tools`
   already allow, so it widens nothing; the prompt's instruction then matches what the session has. Rejected: delaying
   the first turn until the MCP server connects — the adapter cannot observe the session's MCP state.
3. **H2 fallback.** When a created Claude delegation has not registered and the session is idle, `continue` already
   re-sends the registration turn once (round2-fixes D49). Why the failing record went to `unknown` instead is found
   first while building (not yet verified); if it went there only because the first turn ended without a
   registration, it stays `created` with `prerequisite: mailbox-registration-missing` instead, so the re-send path
   applies. A record that is `unknown` for any other reason keeps today's rules, and its error now names the next step:
   `cancel` it, then create again.
3a. **Found while building (2026-10-10, listed separately in the PR).** (i) The prompt: mailbox tools arrive only
   after a tool call, so a turn that ends without one never gets them; the first turn and the re-sent one both say "do
   not end your turn: make one allowed Read of a file you may read for this task, then load them by name with
   ToolSearch and register" (the coordinator asked for the same wording in both). A re-send by wake carries the same
   envelope. (ii) Why the H2 record went `unknown`: `claude --bg --resume <session>` starts a new background job with
   its own id and session id (d849dfa6 resumed as 6472d974), and the adapter required the old id. It now follows the
   id its own resume printed, once that job is listed in the same project, and moves the record's binding to it
   (`rebind_host`, only from the exact old binding, only while `created` or `running`). This is Claude Code's
   resume, not a second session from the adapter. (iii) An `unknown` turn result put the turn ref in `hostStatus`;
   it now says `unknown` with `host-result-unknown`, and a continue of an `unknown` record answers
   `delegation-state-unknown` with "cancel it, then create again". (iv) Real check (a), first run: the resumed
   session's `bridge_register` of the delegation's own name was refused — the name is held by the stopped session
   (new session id). The user chose (2026-10-10) that the resumed turn's envelope, and only that turn's, authorizes
   taking that one name back: when the refusal says the holder is a claude session no longer running, register again
   with `takeover: true` and `wake: null`, then (safe review) with `wake: "auto"`. Two steps because the bridge refuses
   takeover together with a new wake while the old binding exists (bridge gap, not changed here).
4. **L1.** `prune --help` says `--confirm ID,...` cancels the listed ids.
5. **Real checks on this Mac** before the PR: (a) a Codex-shaped Claude delegation (the adapter's own commands, scoped
   to `README.md`) is created, completed, stopped with `claude stop`, then continued through the adapter; the follow-up
   resumes and a read of a file outside the scope is denied. (b) Cold start, where H2 appeared: with every bridge
   stopped (or right after `upgrade --confirm`), three creates in a row; all three register and report back. If any does
   not, assumption 3's fallback must catch it — the record stays `created` with `mailbox-registration-missing` and the
   re-send path completes it — and it must never go to `unknown`. Stopping the bridges needs the user's consent.

## Decisions

- **D181 `done` is a stopped Claude session.** Assumption 1.
- **D182 the delegated session can load its mailbox tools.** Assumptions 2 and 3.
- **D183 truthful help.** Assumption 4.

## Requirements

1. Red first: an adapter test with the verbatim 2.1.295 `done` entry resumes (one `--resume` with the launch limits),
   where today it holds `target-status-unknown`.
2. Red first: every launch shape's `--tools` contains `ToolSearch`; the resume argv matches the create argv as in 0.6.1.
3. Red first: a create whose first turn ends without registration leaves the record `created` with
   `mailbox-registration-missing`, and a later `continue` re-sends the registration; an `unknown` record's continue error
   names `cancel` and create as the next step.
4. `prune --help` text.
5. The real checks of assumption 5 (resume through the adapter; three cold-start creates), recorded in the todo.
6. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Always: limits only narrow or stay equal; `ToolSearch` adds no tool the launch did not already allow.
- Never: create a second session for a stopped one; resume by a short id.

## Acceptance (coordinator, after 0.6.2 — not done here)

- Codex → Claude Code: create → stop → continue reaches the session with its scope and permission intact.
- Ten Codex → Claude Code creates in a row all register and report back (H2 is intermittent).

## Open questions

None. Accepted by the user on 2026-10-10 (reviewed by the round-2 coordinator, 86dbbf7).
