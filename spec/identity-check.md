# Spec: identity-check

## Objective

Make a mailbox identity belong to the host session that registered it: a send (and an acknowledgement) is accepted only
from the session that owns the `from` name; only a message's recipient may reply to it; a name owned by one session
cannot be re-registered or re-bound by another without an explicit takeover; a session that cannot prove its identity
gets clear guidance instead of a bare error; and a Codex session that is auto-approved cannot be bound for wake
(finding 1). Also fix the bridge's mailbox open order (`busy_timeout` after `journal_mode`), found in `idempotency`.
Interface §3 rows 44, 45, 77, 79, §7 rows 126–129, §8 row 136, gap g, finding 1; checklist A2, B7, B8.

Readers: the user; the round 1 coordinator (A2, B7, B8, and round 2 on this Mac); agents building `ops-commands`
(`whoami` reads what this module records).

## What exists today (measured, main 6450d92 and this Mac's running processes, 2026-10-07)

- **Who is calling:** one bridge server process per MCP connection. A Claude-spawned bridge has
  `CLAUDE_CODE_SESSION_ID` in its environment (this session's bridge, pid 30331: yes). The Codex app-server
  (`codex app-server`, pid 48801) runs five bridge processes started at different times, and **none has
  `CODEX_THREAD_ID`, `CODEX_SESSION_ID` or even `PWD`**. So the bridge can verify a Claude caller's session, but not a
  Codex caller's: Codex sessions read `CODEX_THREAD_ID` from their own shell and pass it in `wake: {app, sessionId}`
  (`skills/collab/SKILL.md:27-29`), which the bridge cannot check. `detectSession()` (`server.ts:47-53`) returns
  `null` in a Codex-spawned bridge.
- **Sender:** `bridge_send` `from` is free text; an unregistered sender gets a warning (`server.ts:184-187`). The
  only refusal is `from: "bridge"`. `bridge_ack` takes any `agent`.
- **Names:** `bridge_register` accepts any unused or used name. Re-binding a name whose wake target is a different
  *live* session is refused; a dead Claude target moves silently to the caller (`server.ts:131-142`). No host identity
  is stored with the agent (`agents` table, `schema.ts`), so an unbound name has no owner at all. The process keeps
  the names it registered in memory (`localAgents`, `server.ts:67,149`), used only for defaults.
- **Replies:** since `idempotency`, `replyTo` links a reply to an existing message; anyone may reply.
- **Auto-approval:** not detected. Claude's permission mode is not visible to the bridge (neither in its environment
  nor in `~/.claude/sessions/<pid>.json`, whose keys are cwd, entrypoint, hostSessionId, kind, messagingSocketPath,
  name, pid, procStart, sessionId, status, …). Codex: `~/.codex/config.toml` on this Mac currently has
  `approval_policy = "on-request"`, **`approvals_reviewer = "guardian_subagent"`**, `sandbox_mode =
  "workspace-write"` — so under the rule below a Codex wake binding here would be refused today.
- **Open order:** `BridgeStore` runs `journal_mode = WAL` and `foreign_keys` before `busy_timeout = 5000`
  (`bridge-store.ts:325-327`); a process opening the mailbox while another holds the write lock fails at once with
  "database is locked" (seen in `idempotency`'s race test). The Python readers (`native_collaboration_retire`,
  `session_delegation_backend`) open read-only through `sqlite3.connect`, whose default 5 s timeout applies before
  any statement, and run no pragma.

## Assumptions

Confirmed by the user on 2026-10-07, including schema v5.

1. **Threat model: one user, one Mac.** The goal is to stop mistakes and confused agents — a delegated session sending
   as its origin, two sessions sharing a name, a reply from the wrong party — not a hostile local process, which can
   open the SQLite file directly. Nothing here is a security boundary against the user's own processes.
2. **A session proves an identity in one of two ways:** (a) the name was registered through **this bridge process**
   (the in-memory set, for both hosts); (b) the name's recorded host is a Claude session and equals this process's
   `CLAUDE_CODE_SESSION_ID` (survives a bridge restart). A Codex session after a bridge restart re-registers (allowed,
   see 4) — the guidance text says so. If the Codex app-server ever shares one bridge process between threads, names
   registered by those threads are interchangeable inside it; this residual is documented, not solved.
3. **The host identity is recorded:** schema v5 adds nullable `agents.host_app` and `agents.host_session`, set at
   registration — Claude: the verified env session; Codex: the session it claims in `wake: {app: "codex",
   sessionId}` (marked unverified), else NULL. Python readers accept v2–v5; the v2 → v5 path is tested as in
   `idempotency`. Existing rows keep NULL (no owner) until their first registration after the upgrade.
4. **Takeover needs an explicit flag:** registering or binding a name whose recorded host differs from the caller's
   (both known) is refused unless `takeover: true`; the error says whether the recorded Claude session is still
   running. This replaces today's silent move from a dead Claude session. A name with no recorded host is claimed by
   its next registration. A Claude caller may bind wake only to its own session (`"auto"`, or an explicit
   `{app: "claude"}` equal to its own id).
5. **Only the recipient replies:** a send with `replyTo` must come from the original's `to_agent`; for a broadcast,
   from any agent except its sender. Replies to the bridge's own notices are refused (they say "do not reply").
6. **Auto-approval is checked for Codex only.** Claude's mode cannot be observed by the bridge, so the Claude side stays
   with the skill rule plus Claude's own holding of cross-session messages in bypass mode. Codex counts as
   auto-approved when the top-level `approvals_reviewer` is `"guardian_subagent"` or `approval_policy` is `"never"` in
   `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`); read only, never written. A `[profiles.*]` override is
   not evaluated (documented). An unreadable or malformed config counts as auto-approved (fail closed).
7. The bridge's own sender (`bridge`), the CLI (`claude-codex-bridge` commands run by the user, including the pinned
   retire command) and the Python hooks are not MCP callers and are not checked. `relay_status.py` output and
   `ready` rule unchanged; `interface.json` stays 1.0.

## Decisions

D37–D40 accepted on 2026-10-07; D37 includes `bridge_wait` with `acknowledge: true`.

- **D37 which tools are checked:** `bridge_send` (`from`), `bridge_ack` (`agent`) and `bridge_wait` with
  `acknowledge: true` — the calls that write as an identity. Reading tools (`bridge_inbox`, `bridge_wait`, `bridge_outbox`) and `bridge_retire` stay as they are.
  `bridge_wait` with `acknowledge: true` is checked too (it acknowledges).
- **D38 Codex auto-approval is checked at bind time and at each Codex ping:** a bound Codex session whose config later
  turns auto-approved gets its pings `held` with a reason instead of sent, and the binding is not removed (switching
  back resumes). Alternative: bind time only.
- **D39 guidance text** for an unproven sender: names the identity, says why (not registered through this session),
  and gives the one next step (`bridge_register` with this name from this session; `takeover: true` only after the
  user agrees). Same shape for a missing Codex session id: "pass `wake: {app: \"codex\", sessionId: <CODEX_THREAD_ID>}`;
  never guess from titles or processes".
- **D40 busy_timeout first:** set `busy_timeout` before any other statement on open; regression test: one process
  holds the write lock, another opens and reads and writes within the timeout. Own task, own commit. The Python
  readers get an explicit `timeout=5` (same value as today's default) so the behaviour is pinned.

## Requirements

1. Sender check (assumption 2, D37) with tests: registered through this process → accepted; Claude name recorded for
   this session in a new process → accepted; other session's name → refused with D39 text; `bridge` notices, CLI
   unaffected; delegation result route (target registers then sends) still works (existing tests green).
2. Schema v5 and Python readers (assumption 3), v2 → v5 tested, older-process inserts still work.
3. Takeover (assumption 4) with tests: same session re-registers freely; other known session refused without
   `takeover`; accepted with it; NULL-owner name claimed; Claude caller cannot bind another Claude session.
4. Reply rule (assumption 5) with tests, including broadcasts and bridge notices.
5. Codex auto-approval (assumption 6, D38) with tests on fixture config files: guardian, `never`, normal, missing file,
   unreadable or malformed file (refused, fail closed); bind refused; pings held.
6. D40 with the cross-process regression test.
7. Docs: README, collab and collaboration-ops skills (takeover asks the user; guardian blocks wake), interface rows,
   checklist A2, B7, B8, `UPSTREAM.md` / `UPSTREAM.sha256`.

## Testing strategy

TS unit tests in the bridge (MCP-level tests run the server with and without `CLAUDE_CODE_SESSION_ID`, and with a
fixture `CODEX_HOME`); Python tests for v5 readers. Live (temporary `AGENT_RELAY_HOME`, coordinator told first, no host
config change): B8 (reply as a non-recipient refused), sender check across two Claude bridge processes, and B7 with a
fixture `CODEX_HOME` — the real `~/.codex/config.toml` is only read.

## Boundaries

- Always: read host config only; keep existing names and messages; additive migration.
- Ask first: writing any host config; treating Claude sessions as auto-approved by guess.
- Never: guess a session from titles, processes or recent activity; push without approval.

## Success criteria

1. All tests green, including cross-process open, takeover and sender tests.
2. Live B7, B8 and the sender check pass against the target column.
3. Docs updated; round 2 warned that this Mac's Codex selector must be 请求批准 for Codex wake.

## Open questions

None. (An unreadable or malformed Codex config refuses the binding and holds pings — user, 2026-10-07.)
