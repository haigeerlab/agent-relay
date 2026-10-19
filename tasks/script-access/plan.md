# Plan: script-access

<!-- spec-guard: review approved -->


Based on [`spec/script-access.md`](../../spec/script-access.md) (accepted by the user on 2026-10-20: assumptions 1–6,
D240–D245, both open questions resolved as proposed). This branch (`claude/script-access`) carries the map row, spec
and plan as one PR; the implementation goes on `claude/script-access-impl` from main after that PR is merged. Released
as 0.9.0 (interface 2.8, mailbox schema 7 unchanged) in a separate release PR. The round-2 coordinator is told every PR
number.

## Task List

### Task 1: read-only store (D242)
Red first in `bridge/test/script-access.test.ts`: `new BridgeStore(path, { readOnly: true })` opens with SQLite
`mode=ro`; a write throws; a mailbox one schema behind is not migrated and refuses with a readable error; reads do not
call `expireDue` (an overdue message stays `queued` in the read-only view while a normal store expires it). Then
`BridgeStore` gains the option; every `expireDue` call site is skipped when read-only.

### Task 2: shared views (D241)
Red first: for one mailbox (fake Claude registry, fake ChatGPT socket from `test/support/fake-codex-app.ts`), the new
`agentsView`, `outboxView` and `sessionsView` return exactly what `bridge_agents` (no parameters), `bridge_outbox
{agent}` and `bridge_sessions` return over MCP. Then move the three handlers' bodies out of `server.ts` into a new
`src/views.ts`; the MCP tools call the functions; `sessionsView` takes the caller context (`thisSession`,
`codexSessionId`, channel mode) as input, null for a script. No change to the MCP output (existing MCP tests stay
green unchanged).

### Task 3: script identity (D244)
Red first: `register-script-identity <name>` without `--confirm` prints what it would do and changes nothing; with it,
the agent row has host `{app: "script", sessionId: name}` and no wake binding; a Claude-verified or Codex caller cannot
register, takeover-free, or act as that name (`IdentityError` with a sentence naming the script identity); with
`takeover` a session may take it over as today. Presence of a script identity is `unknown` with detail "script
identity". Then `AgentHost.app` adds `"script"`, `CallerIdentity` treats a recorded script host as owned by no session,
and `presence.ts` maps it; the CLI owns exactly the script identities.

### Task 4: CLI commands (D241, D242, D243)
Red first, running the built `dist/cli.js` as a child process against a temporary mailbox: `agents`, `outbox <name>`,
`sessions` print one JSON object equal to the views (Task 2) and leave the mailbox unchanged (row counts, `read_at`,
acknowledgements, `last_seen`); `send --from <script identity> --to <name> --body-file <path>` (or stdin) prints
`bridge_send`'s object, refuses a non-script `--from`, refuses a body on argv, honours `--expects-reply`,
`--reply-to`, `--thread`, `--also-answers`, `--withdraws`, `--idempotency-key`, `--no-wake`, and pings a bound fake
Claude session exactly once before exiting; a missing runtime, mid-swap state or schema mismatch exits non-zero with
one stderr sentence. Then `cli-logic.ts` gains the commands and parsing, `cli.ts` wires them (read-only store for
reads; one `deliver` then one dispatcher flush limited to that message for `send`).

### Checkpoint (report): bridge green
`npm run check` in `bridge/`; the MCP output tests unchanged and green.

### Task 5: launcher, doctor, rollback, uninstall (D240)
Red first in `hooks/test_native_collaboration_runtime.py` (and the doctor test): install and upgrade write
`~/.agent-relay/bin/agent-relay` (0700, absolute node from `shutil.which`, refusing a relative one; runtime path and
env written in) and verify it with `--version`; rollback rewrites it for the previous runtime; uninstall removes it;
under `env -i PATH=/usr/bin:/bin HOME=<tmp>` the launcher runs `agents` on a temp runtime; `doctor` reports
`script-launcher` ok, and warn when missing, wrong mode, pointing at another runtime, or its node gone. Then
`native_collaboration_runtime.py` and `native_collaboration_doctor.py`.

### Task 6: interface 2.8 and docs (D245)
`interface.json` 2.8 with the `script` block; `test_packaging`; `relay_status.py` docstring;
`docs/collaboration-interface.md` (version line, a "Script commands" section: argv, output = the MCP rows, exit codes,
read-only promise, script identity, wake limits H1/H4/not-loaded); README (zh/en) "scripts and launchd" section;
`collaboration-ops` skill (how the user registers a script identity, with `--confirm`); `UPSTREAM.md` row and manifest;
`bridge/CHANGELOG.md` 0.9.0; CHANGELOG `[Unreleased]` (runtime `upgrade --confirm` writes the launcher; a 0.8.x bridge
shows a script identity as `unknown`/`not-loaded` and cannot act as it).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 7: PR and CI
Push `claude/script-access-impl`, open the PR, ask the round-2 coordinator to review; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.9.0 release PR, tag and real-host upgrade, each with the user's
approval; real-host acceptance as the spec lists (a launchd job, a test script identity, a wake-bound test session,
the plugin from the checkout under `~/Documents`); tell the requesting session when 0.9.0 ships.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Moving the handlers changes MCP output | consumers that parse the MCP results break | Task 2 is a pure move; existing MCP tests stay unchanged; a new test compares CLI and MCP output |
| A read path still writes (an `expireDue` or migration missed) | the "read-only" promise is false | `mode=ro` makes any write throw; Task 4 asserts the mailbox unchanged after each read |
| The launcher points at a node that later moves (nvm upgrade) | launchd runs fail | `doctor` `script-launcher` warns; `upgrade --confirm` rewrites it; exit non-zero with one sentence |
| A 0.8.x bridge meets a script identity during the upgrade | it may show odd presence | it already refuses to act as it (D38); CHANGELOG caveat; presence `unknown` |
| `send`'s one flush races a running bridge's dispatcher | the ping is sent twice | the dispatcher's claim (`claim()` with `attempt_id`) already serialises one job across processes; a test runs both |
| launchd still cannot read something the CLI touches | exit 126 or permission errors | acceptance runs it from a real launchd job with the plugin under `~/Documents`; the CLI reads only `~/.agent-relay`, `~/.claude/sessions`, the ChatGPT IPC socket |
