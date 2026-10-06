# Spec: state-migration

## Objective

Move a user's Spec Guard-era collaboration data into agent-relay without losing anything: detect the old state,
check it is safe to move, back it up, copy it into agent-relay's locations, verify the counts match, and report
the host entries and permission rules the user still has to switch. The old directories are never deleted by the
tool. This is the last translation module; the real migration on this Mac happens in integration round 1
(checklist D7).

Readers: the user reviewing the split; users upgrading from Spec Guard's collaboration; Spec Guard's
`collaboration-dependency`, which points users here.

Sources: [the interface document](../docs/collaboration-interface.md) §13 (migration row, D1, D9, D12); this
repository's `spec/cross-host-delegation.md` (D12); measured state on this Mac (2026-10-07, structure and counts only):

| Old state | Measured |
|---|---|
| `~/.spec-guard/native-collaboration/` (0700) | pinned bridge checkout + `node_modules`, `manifest.json`, `mailbox/` (`bridge.sqlite` with WAL/SHM, `backups/` 7 daily copies, 5.6 MB), `data/claude-codex-bridge/runs/`, and `host-config-backup.v7xZtz/` (copies of host configs, not created by Spec Guard code) |
| mailbox tables | messages 83, acknowledgements 83, agents 62, wake_jobs 60 (accepted 1, cancelled 17, read 39, unknown 3), meta 1, others 0 |
| `~/.spec-guard/session-delegation/delegation.sqlite` (0700) | authorizations 7 (all cancelled); delegations 7: cancelled 6, **creating 1** (`27f0de…`, never launched — baseline finding 3) |
| running old bridge servers | 8 processes of `~/.spec-guard/native-collaboration/dist/server.js` (open sessions with the old MCP entry) |
| `~/.spec-guard/collaboration/` | retired XATS history — not migrated, not deleted (interface §13) |

## Assumptions

Confirmed by the user on 2026-10-07:

1. **Data only.** The tool moves the mailbox data (`mailbox/bridge.sqlite`, `mailbox/backups/*`, `data/`) and the
   delegation database. It does not copy the bridge checkout or `node_modules` (agent-relay installs its own pinned
   runtime) and never copies `host-config-backup.*` (host configuration copies are not collaboration data).
2. **Copy, never move or delete.** The old directories stay as they are; the tool prints how to remove them by hand
   once the user is satisfied. SQLite files are copied with SQLite's backup API, so WAL content is included and the
   copy is consistent.
3. **Host entries are reported, not changed.** The tool reads `~/.claude.json` and `~/.codex/config.toml` to report
   whether the old `spec-guard-native-collaboration` / `spec_guard_native_collaboration` entries and the new
   `agent-relay` / `agent_relay` entries exist, and prints the next steps: attach the new entries through
   `collaboration-ops`; remove the old ones with Spec Guard's own uninstall (it installed them, so it can remove them
   by exact match); rename project allow rules to `mcp__agent-relay__bridge_*` by hand.
4. **Two commands.** `state_migration.py detect` (read-only report, always safe) and
   `state_migration.py migrate --confirm` (does the work). Both accept `--home` for tests; nothing else is
   configurable.
5. **Verification is unit tests plus one rehearsal on a copy.** The rehearsal copies this Mac's old data files (not
   reading message bodies) into a scratch home, installs the pinned runtime there, runs `migrate`, and compares
   counts; the real migration waits for round 1.

## Decisions

All three taken as recommended by the user on 2026-10-07.

- **D12 refinement — the stale `creating` delegation.** As written, D12 blocks migration while any old delegation is
  non-terminal, and this Mac has one (`27f0de`, `creating`, no host session ever attached) that cannot be cancelled
  cleanly (finding 3), so migration would be blocked forever. Decision: a non-terminal delegation **that never
  got a host session** may be acknowledged explicitly with `--acknowledge-stale <id-prefix>` after the tool shows
  it; it is then copied as-is. A non-terminal delegation that has a host session always blocks.
- **D13 running old servers.** Messages that arrive in the old mailbox after the copy would exist only there.
  Decision: `migrate` refuses while any old bridge server process is running and lists how many; the user closes
  or restarts those sessions first.
- **D14 target must be fresh.** `migrate` requires agent-relay's runtime to be installed (`status`
  ready) with an empty mailbox (no messages, no agents) and no delegation database yet; it never merges two
  mailboxes. If the user already used agent-relay, the tool stops and explains.

## Requirements

1. `detect`: prints old and new locations with existence, the table counts above, non-terminal delegations
   (id prefix, state, launched or not), non-final wake jobs (pending/sending/accepted/unknown, reported only), running
   old server count, host entry presence, and the verdict `ready` or the list of blockers. Writes nothing.
2. `migrate --confirm`: re-runs every check; on any blocker stops without writing. Otherwise:
   backup → `~/.agent-relay/backups/<UTC timestamp>/` (0700; files 0600) with the old mailbox, backups, data, and
   delegation database; copy into `~/.agent-relay/runtime/mailbox/`, `runtime/data/`, and
   `~/.agent-relay/delegation/delegation.sqlite` with the modes agent-relay expects (runtime `status` must still
   report ready afterwards); verify that every table's row count in each copy equals the source snapshot; print the
   report and the host next steps.
3. On a verification mismatch the tool reports it, leaves the backup, and removes nothing.
4. `collaboration-ops` skill and README gain a short "migrate from Spec Guard" section pointing to the two commands.
5. Interface §13 migration row updated to the D12 refinement, D13, D14.

## Commands

```bash
/bin/bash scripts/validate.sh
python3 -B plugins/agent-relay/hooks/state_migration.py detect
python3 -B plugins/agent-relay/hooks/state_migration.py migrate --confirm [--acknowledge-stale <id-prefix>]
```

## Project structure

New: `plugins/agent-relay/hooks/state_migration.py`, `plugins/agent-relay/hooks/test_state_migration.py`.
Changed: `skills/collaboration-ops/SKILL.md`, `README.md`, `docs/collaboration-interface.md` §13.

## Testing strategy

- Unit (fixture homes with real table schemas): detect report; each blocker (launched non-terminal delegation,
  unacknowledged stale one, running server via an injectable process lister, target not installed, target mailbox
  used, delegation db present); a successful migration with matching counts, modes, and runtime still ready; old
  files unchanged byte-for-byte; backup present; a forced count mismatch reported without deletion.
- `detect` on this Mac (read-only) recorded in todo.md.
- Rehearsal on a scratch copy (assumption 5), needs network for the runtime install; approval asked at Plan review.

## Boundaries

- Always: copy, verify, report; keep old data untouched.
- Ask first: the scratch rehearsal; anything that writes outside `~/.agent-relay` or the scratch home.
- Never: delete or edit `~/.spec-guard/`; read message bodies; change host configuration or permission files;
  migrate the retired XATS history; push the repository.

## Success criteria

1. All blocker and success tests pass; old files unchanged after migration.
2. `detect` on this Mac reports the measured state and its blockers truthfully.
3. The rehearsal migrates the copied data with every count matching.

## Open questions

None; the D12 refinement, D13 and D14 are decided.
