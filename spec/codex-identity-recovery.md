# Spec: codex-identity-recovery

## Objective

First of the three modules of 0.7.1 (bridge). From a usage report relayed on 2026-10-16 by an observing Claude
session (mailbox name `agent-relay-observer`, read of both hosts' session logs 2026-10-02 to 10-16, about 11 000
mailbox calls, about 100 failed), with the user's decision the same day ("三条假设按你的推荐通过，第 2 条选 (b)，发
0.7.1"): long-running Codex tasks lose their mailbox identity when their bridge process is replaced, and then
`bridge_send` / `bridge_ack` fail with `not an identity of this session` (20 calls in 4 Codex tasks, each after a
successful registration of the same name with wake `{app: "codex", sessionId}`). Separately, during the 2026-10-15
runtime upgrade open Codex tasks kept retrying calls that failed with `Transport closed` (20 calls).

## What exists today (main d188a92, v0.7.0)

- `bridge/src/identity.ts` `CallerIdentity`: a Claude caller's host comes from `CLAUDE_CODE_SESSION_ID` in the
  bridge's environment and is verified; a name recorded for that host stays this session's across bridge restarts.
  A Codex caller has no host (checked again 2026-10-16 on all six ChatGPT-started bridge processes: no session id in
  their environment), so a name is proven only inside the bridge process that registered it (`proven`). A new process
  (ChatGPT restart, task reloaded) knows nothing.
- `require()` then throws `"<name>" is not an identity of this session … call bridge_register with agent "<name>" from
  this session again.` and, because the recorded host is a Codex session that differs from "no host", adds
  ` It is recorded for another codex session; registering it here needs takeover: true, which only the user may
  approve.` For the task's own name that sentence is wrong: `bridge_register` with the same
  `{app: "codex", sessionId}` succeeds without takeover (server.ts register: no owner conflict when the claimed host
  equals the recorded one).
- `skills/collab/SKILL.md` already says (codex-not-loaded D200): register again with the same name and
  `{app: "codex", sessionId: CODEX_THREAD_ID}`, no takeover. The same paragraph also says "报错说名字属于另一个会话时，
  换一个名字" — which the misleading sentence triggers, so a task may rename itself instead of re-registering.
- No skill tells a session what `Transport closed` means; `skills/collaboration-ops` only tells the user, after a
  `pkill`, to reopen the apps.

## Assumptions (accepted by the user 2026-10-16)

1. The bridge cannot restore a Codex identity by itself: the only task id it could use is the one the task reports,
   which proves nothing (D200 stands). No new parameter on `bridge_send` / `bridge_ack`: sessions already open keep
   their old tool definitions (0.7.0 finding), so it would not help the sessions that hit this.
2. The refusal for an unverified caller and a name recorded for a Codex task says what to do, in a form to copy:
   register again with the same name and the task's own `{app: "codex", sessionId: "<CODEX_THREAD_ID>"}` (as `wake`, or
   as `host` when it must not be woken), no takeover needed when it is this task's own name, then repeat the call; if
   the name is not this task's, use its own name. The takeover sentence is dropped for this case and kept for a
   verified caller whose name is recorded for another session.
3. The skill: on this refusal, register again and repeat the call without asking the user; rename only when the
   refusal says the name belongs to another session for a verified (Claude) caller, or registration itself is refused.
   On `Transport closed`, stop retrying mailbox calls and tell the user the connection to the mailbox ended (usually a
   runtime upgrade or ended bridge): quit the ChatGPT app completely (⌘Q) and reopen it for Codex, open a new session for
   Claude Code; after that, register again with the same name.
4. Release 0.7.1 with the other two modules; interface 2.2 (set by `read-own-sent`), schema 6 unchanged.

## Decisions

- **D209 a refused Codex caller is told to register its own name again, with the exact call, not to take over.**
  Applies when the caller has no verified host and the name's recorded host is a Codex session. Unregistered names and
  verified callers keep their current refusals.
- **D210 sessions stop on `Transport closed` and hand the restart to the user.** Skill text only; the bridge cannot
  answer a closed transport.

## Requirements

1. Red first, `bridge/test/`: an unverified caller acting as a name recorded for a Codex host gets a refusal that
   contains `bridge_register`, the name, `{app: "codex", sessionId: "<CODEX_THREAD_ID>"}`, says no takeover is needed
   for its own name and to repeat the call, and does not contain `takeover: true`; following it (register with that
   host, no takeover) succeeds and the original call then passes. A verified caller whose name is recorded for another
   session keeps the takeover sentence; an unregistered name keeps its refusal.
2. `skills/collab/SKILL.md`: the identity paragraph says to register again and repeat on this refusal (no user
   question, no rename), and the `Transport closed` rule of assumption 3; `skills/session-routing` points to it where
   it handles send failures.
3. `bridge/INSTRUCTIONS.md` and the server instructions say the same in one sentence each (bridge docs change anyway in
   this release).
4. CHANGELOG, `UPSTREAM.md` and manifest (D24); `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24
   first on PATH; CI green.

## Out of scope

- Automatic identity recovery inside the bridge, or any proof of a Codex caller.
- Changing retry behaviour of hosts on a closed transport.

## Boundaries

- Never: accept a self-reported thread id as proof, weaken takeover rules, or touch host settings.

## Acceptance (round-2 coordinator, after 0.7.1)

- In a test Codex task registered with wake, end its bridge process (or restart the ChatGPT app): the next send is
  refused with the copyable re-registration, the task re-registers without takeover and resends on its own.
