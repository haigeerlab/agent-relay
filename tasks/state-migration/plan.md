# Plan: state-migration

Based on [`spec/state-migration.md`](../../spec/state-migration.md) (reviewed by the user on 2026-10-07, D12
refinement, D13, D14 accepted). Repository `/Users/vilin/Documents/haigeerlab/agent-relay`, branch `main`, local only.
Reread [`docs/collaboration-split-brief.md`](../../docs/collaboration-split-brief.md) after any context reset.

## Overview

Build the read-only `detect` first (it is also the check list `migrate` re-runs), then `migrate`, then the docs, then
prove it on this Mac read-only and on a scratch copy.

## Architecture Decisions

- One module `state_migration.py` with pure functions over a `home` path: `inspect(home)` returns facts and blockers;
  `migrate(home, acknowledged)` calls `inspect` again and only then writes. The process lister is a parameter so tests
  can inject running servers.
- Old names (`~/.spec-guard/…`, `spec-guard-native-collaboration`, `spec_guard_native_collaboration`) appear only in
  this module as the migration source, as named constants; the name scan lists them as deliberate.
- SQLite copies use `sqlite3.Connection.backup`; sources are opened read-only (`mode=ro`).
- Count check compares every user table of each copied database with the source snapshot taken in the same run.
- Reuse `native_collaboration_runtime.status`/`default_root` and `session_delegation_control.default_state_root` for the
  target paths.
- Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: `detect`

**Description:** Facts and blockers per Spec requirement 1: old and new paths, table counts, non-terminal delegations
(launched or not), non-final wake jobs, running old servers (`ps -axo command` matching the old server path), host
entries from `~/.claude.json` and `~/.codex/config.toml` (presence only), target freshness (D14). Blockers: launched
non-terminal delegation; never-launched non-terminal delegation not acknowledged; running old server (D13); target
runtime not ready; target mailbox not empty; target delegation db present. Tests with fixture homes.

**Acceptance:** detect tests pass; `detect` on this Mac prints the measured counts and blockers (stale `27f0de` not
acknowledged, 8 servers running, runtime not installed) and writes nothing.

**Verify:** `scripts/validate.sh`; one live `detect` recorded in todo.md.

**Files:** `hooks/state_migration.py`, `hooks/test_state_migration.py`

### Task 2: `migrate`

**Description:** Backup, copy, mode fix, count verification, report, host next steps (Spec requirements 2–3);
`--acknowledge-stale` by id prefix (must match exactly one never-launched non-terminal delegation). Tests: success
path (counts, modes, runtime still ready, old files byte-identical, backup present), each blocker writes nothing, a
forced mismatch is reported without deletion.

**Acceptance:** migrate tests pass.

**Verify:** `scripts/validate.sh`.

**Files:** `hooks/state_migration.py`, `hooks/test_state_migration.py`

### Checkpoint (report): detect and migrate pass their tests

### Task 3: Docs and interface

**Description:** "Migrate from Spec Guard" section in `skills/collaboration-ops/SKILL.md` and `README.md`; interface
§13 migration row updated (D12 refinement, D13, D14, copy-only, host entries reported).

**Acceptance:** runner green; README section present.

**Verify:** `scripts/validate.sh`.

**Files:** `skills/collaboration-ops/SKILL.md`, `README.md`, `docs/collaboration-interface.md`

### Task 4: Rehearsal on a scratch copy (network, approval)

**Description:** Scratch home in the session scratchpad; copy this Mac's old `mailbox/`, `data/` and
`delegation.sqlite` into its `.spec-guard/…` (file copy via SQLite backup, no body reads); install the pinned runtime
into its `.agent-relay/runtime`; `detect` (expect the stale-delegation blocker only, since the process check looks for
servers on the scratch path); `migrate --confirm --acknowledge-stale 27f0de`; record counts; delete the scratch home.

**Acceptance:** every table count matches; runtime status ready after migration; scratch removed.

**Verify:** the recorded report.

**Files:** `tasks/state-migration/todo.md`

### Checkpoint (gate): module review

Stop and report per the brief format. Never pushed.

## Risks

- The running-server check matches by command path; a server started from a different checkout path would be missed.
  It is reported as a limit, not presented as proof that nothing writes the old mailbox.
- `~/.claude.json` is large and holds other settings; only the `mcpServers` keys are read and nothing is printed except
  presence.
