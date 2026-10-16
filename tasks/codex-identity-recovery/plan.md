# Plan: codex-identity-recovery

Based on [`spec/codex-identity-recovery.md`](../../spec/codex-identity-recovery.md) (accepted by the user on 2026-10-16,
D209, D210). The three 0.7.1 modules are built in one implementation branch, `claude/relay-071-impl`, from main after
this plan's PR, in map order (this module, then `reply-own-message-guidance`, then `read-own-sent`); `activeModule`
moves to the next module only when this module's todo is fully checked. One implementation PR, reviewed by the round-2
coordinator; the 0.7.1 release PR waits until it is merged.

Every commit that changes a file under `plugins/agent-relay/bridge/` reruns `python3 scripts/bridge-manifest.py` and
adds its `UPSTREAM.md` row in the same commit (D24).

## Task List

### Task 1: the refusal for an unverified Codex caller (D209)
Red first (requirement 1), `bridge/test/identity.test.ts`: an unverified caller (no host) acting as a name recorded
for a Codex host is refused with text containing `bridge_register`, the name,
`{app: "codex", sessionId: "<CODEX_THREAD_ID>"}`, "no takeover" for its own name and "repeat", and not `takeover: true`;
a verified (Claude) caller whose name is recorded for another session keeps the takeover sentence; an unregistered
name keeps its refusal. An MCP-level case in `host-claim.test.ts` (or the identity test's server harness): after the
refusal, `bridge_register` with `host: {app: "codex", sessionId}` and no takeover succeeds and the same `bridge_send`
then passes, wake binding unchanged.
Green: `identity.ts` `require()` branches on `!this.host && agent.host?.app === "codex"`.
Files: `src/identity.ts`, `test/identity.test.ts`, `test/host-claim.test.ts`.

### Task 2: skills and instructions (D209, D210)
`skills/collab/SKILL.md`: the identity paragraph says that on this refusal the session registers again with the same
name and repeats the call, without asking the user and without renaming; renaming applies only when registration
itself is refused for another session. Add the `Transport closed` rule (stop retrying; Codex: ⌘Q and reopen the
ChatGPT app; Claude Code: open a new session; then register again with the same name). `skills/session-routing`
points to it where send failures are handled. One sentence each in `bridge/INSTRUCTIONS.md` and the server
instructions (`server.ts`, asserted through `getInstructions()` in an existing test).
Files: two `SKILL.md`, `bridge/INSTRUCTIONS.md`, `src/server.ts`, one test, skill entry-point tests if they pin text.

### Checkpoint (report): bridge green
`npm run check` in `plugins/agent-relay/bridge`.

### Checkpoint (report): module done
Todo checked; `activeModule` → `reply-own-message-guidance`.
