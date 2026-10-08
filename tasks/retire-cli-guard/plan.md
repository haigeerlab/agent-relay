# Plan: retire-cli-guard

Based on [`spec/retire-cli-guard.md`](../../spec/retire-cli-guard.md) (accepted by the user on 2026-10-08:
assumptions 1–8, D111–D113). Branch `claude/retire-cli-guard` from main 52012f0. Red → green, one commit per task.
The round-2 coordinator reviews the PR before the user merges. No release in this module.

Code: `bridge/src/cli.ts`; tests: `bridge/test/cli.test.ts`. After any change under `bridge/` (tests included)
regenerate `UPSTREAM.sha256`. Record validate only after its output says `validate: pass`.

## Task List

### Task 1: retire refuses without BRIDGE_DB_PATH; help says so (D111, D112)
Red first in `cli.test.ts` (temporary HOME and `XDG_DATA_HOME`): an existing default database with one agent and no
`BRIDGE_DB_PATH` → `retire <name>` exits 2, stderr names `native_collaboration_retire.py`, bytes and mtime unchanged,
agent not retired; no default database (unset, and `"  "`) → exit 2, nothing created under the data home; `help`
without the variable exits 0 and mentions it. Then `cli.ts`: read and trim the variable before `new BridgeStore`,
refuse with exit 2; one usage line. Existing CLI tests unchanged. `UPSTREAM.md` row, manifest, CHANGELOG.

### Task 2: docs (D113)
Bridge README retire section and the collaboration-ops skill: do not run `dist/cli.js` directly; it refuses without
`BRIDGE_DB_PATH`. Manifest if a bridge file changed.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 3: live check
`mktemp -d` HOME with `AGENT_RELAY_HOME` inside: install a runtime from this branch, plant a default database under
the data home, `node dist/cli.js retire x` without the variable → exit 2, planted file unchanged; register an identity
and retire it with `native_collaboration_retire.py --name … --confirm-retire` → retired. Temporary HOME to the Trash.

### Checkpoint (gate): module review
Then push and PR with the user's approval; the round-2 coordinator reviews; the user merges after CI is green.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The Python retire path breaks | Medium | `test_native_collaboration_retire.py` and the existing CLI retire test stay unchanged and green |
| A test opens the real default database | Medium | every CLI spawn gets a temporary HOME and `XDG_DATA_HOME` |
