# Plan: safe-uninstall

Based on [`spec/safe-uninstall.md`](../../spec/safe-uninstall.md) (accepted by the user on 2026-10-07: assumptions 1–5,
D46–D48). Branch `claude/safe-uninstall` from main 49ef6ba. No bridge change. Red → green each task.

## Task List

### Task 1: Codex removal with approval subtables and a line report (assumptions 1, 2)
`remove_codex_table` parses every `[mcp_servers.agent_relay…]` table (bare or quoted name): the main table and its
`.env` must equal the fragment (the `command` line may differ only by another absolute executable node path), extra
`.tools.<name>` tables may hold only one `approval_mode = "<string>"` line; all of them are removed as one block.
Anything else refuses with every differing line (`line N: …`). Fixture = this Mac's shape (five subtables), plus
extra key, changed value, subtable with two keys, interleaved foreign table, node path change. **Files:**
`hooks/host_config_removal.py`, its tests.

### Task 2: Backups before every host write (assumption 3)
`backup_host_files(paths) -> Path` copies existing files (0600) into `$AGENT_RELAY_HOME/backups/<UTC>/host-config/`
(0700), records missing ones in a `missing.txt`; a failure raises before any write. Called by `install-codex`,
`install-claude` (settings + `~/.claude.json`), `uninstall-codex`, `uninstall-claude`; each prints the backup path.
**Files:** `hooks/native_collaboration_adapters.py` (or new `hooks/host_backup.py`), tests.

### Checkpoint (report): Codex removal and backups green

### Task 3: Claude deny rules removed on uninstall (D46)
`uninstall-claude` removes exactly the seven `mcp__agent-relay__*` deny rules from `settings.json` (atomic write, after
the backup), leaving every other rule and key byte-identical in meaning; absent rules are fine. Tests.

### Task 4: Runtime uninstall keeping history (D47)
`native_collaboration_runtime.py uninstall --confirm`: refuses while a bridge server of this runtime runs; removes the
build (everything except `mailbox/` and `data/`); `status` reports `uninstalled` with `history` path; `install` rebuilds
into a root that holds only `mailbox/` and `data/`, keeping them; `doctor` reports it. Tests (fake npm as existing
install tests).

### Task 5: Docs (D48)
README §卸载 procedure; collaboration-ops skill; interface rows 66, 248, 249, gap k; checklist D17; round 1 finding 6
reference.

### Task 6: Live (temporary `AGENT_RELAY_HOME` and HOME, coordinator told first)
Install runtime and both host entries into a temporary HOME (fake `claude` CLI recording calls, real file writes),
add the five approval subtables, run `doctor`, uninstall both hosts and the runtime, check backups and the kept
mailbox, `doctor` again, then `install` again around the kept mailbox. Real host files untouched (mtimes checked).

### Checkpoint (gate): module review
