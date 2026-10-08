# Plan: legacy-cli-cleanup

Based on [`spec/legacy-cli-cleanup.md`](../../spec/legacy-cli-cleanup.md) (accepted by the user on 2026-10-08:
assumptions 1–7, D95–D98). Branch `claude/legacy-cli-cleanup` from main 931ce63. Red → green, one commit per task.
Second module of 0.5.0; no release at its end.

## Task List

### Task 1: the TS CLI keeps only `retire` and `help` (D95)
Red first in `test/cli.test.ts`: the parser refuses `setup`, `doctor`, `status`, `demo`, `prune`, `backup`, `rollback`,
`uninstall` (usage, exit 2) and still parses `retire <agent> [--note] [--keep-backlog]` and `help`; a test runs
`retire` through the CLI on a temporary mailbox and checks the output, exit code and `--keep-backlog`. Then cut
`cli.ts` / `cli-logic.ts` down; delete `runtime.ts`, `codex-config.ts`, `diagnostics.ts`, `findStaleAgents` (and its
test), `scripts/mailbox-request.ts` and the CLI tests of removed helpers.
Verify: `npm run check`; Python retire tests. `UPSTREAM.md`, manifest, CHANGELOG.

### Task 2: names (D96)
Red first: an MCP test that `initialize` returns `serverInfo.name` `agent-relay`; `cli.test` checks the help names
`agent-relay-bridge`. Then `server.ts` name and log prefix, `package.json` name and `bin`, `package-lock.json` root name
(regenerated with `npm install --package-lock-only`, no dependency change), help text.
Verify: `npm run check`; `npm ci --ignore-scripts` in a copy succeeds. `UPSTREAM.md`, manifest, CHANGELOG.

### Task 3: Python doctor option and retire docstring (D97)
Red first: doctor's parser rejects `--claude-settings`. Then drop it from `native_collaboration_runtime.py` and the
`doctor()` parameter; fix `native_collaboration_retire.py:5`.

### Checkpoint (report): bridge check, validate on one Python

### Task 4: docs (D98)
Bridge README (install, maintenance, storage point to agent-relay's Python runtime; the remaining TS commands), bridge
CHANGELOG, agent-relay README if it names the TS CLI, CHANGELOG `[Unreleased]`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 5: live upgrade from v0.4.0 and retire
`mktemp -d` HOME: v0.4.0 runtime and hosts → `upgrade --confirm` (runtime install runs `npm ci` on the renamed
package) → probe 10 tools, doctor all ok, `native_collaboration_retire.py --name <x> --confirm-retire` retires an
identity with no backlog. Temporary HOME to the Trash.

### Checkpoint (gate): module review
Then push and PR with the user's approval; tell the round-2 coordinator.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `retire` output or exit codes change and the Python retire script misreads them | High | Task 1 retire test through the CLI; Python retire tests; Task 5 live retire |
| Lock file rename breaks `npm ci` in the runtime install | Medium | Task 2 `npm ci` check; Task 5 live upgrade |
| A test helper still imports a removed module | Low | `tsc` in `npm run check` |
