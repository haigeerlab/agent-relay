# Plan: ops-commands

Based on [`spec/ops-commands.md`](../../spec/ops-commands.md) (accepted by the user on 2026-10-07: D41–D45, one
read-only `doctor` run on the real environment). Branch `claude/ops-commands` from main 114ea60. Every bridge change
updates `UPSTREAM.md` and `UPSTREAM.sha256` (`scripts/bridge-manifest.py`) in the same commit; red → green each task.

## Task List

### Task 1: Body from file (D43)
`bridge_send.bodyFile`; exactly one of `body`/`bodyFile`; absolute, regular, not a symlink, owner, ≤ 256 KiB, UTF-8;
read with `lstat` + `open` and compared so a swap between check and read is refused. Tests per spec req 3 (D16).
**Files:** new `src/body-file.ts`, `src/server.ts`, new `test/body-file.test.ts`.

### Task 2: Status and wait by message id (D45)
`messageStatus(id)` in the store: message summary, `deliveryState`, wake job, `acknowledgedAt`, `replies`,
`expiresAt`, `outcome` (`acknowledged` | `replied` | `failed` | `expired` | `pending`). `bridge_wake_status({messageId})`
returns it; `bridge_wait({agent, messageId})` polls it (same wait machinery) until an outcome or timeout, acknowledges
nothing; caller identity = sender or recipient (the `identity-check` rule for `agent`). **Files:** `src/bridge-store.ts`,
`src/server.ts`, new `test/message-status.test.ts`.

### Task 3: whoami (assumption 3)
`bridge_sessions` adds `whoami`: host (verified Claude / unknown), Claude registry title and `cwd` basename for this
session, identities (proven here or recorded for this host) with wake and recorded host. **Files:** `src/server.ts`,
`src/identity.ts`, `test/identity.test.ts`.

### Checkpoint (report): bridge commands green

### Task 4: doctor (D42)
`native_collaboration_runtime.py doctor [--codex-config --claude-json --claude-settings --claude-sessions]` (defaults
under `$HOME`), read-only; checks of D42, each `{check, state, detail, next}`; overall `state`; exit 1 only on `fail`.
Codex auto-approval parsed with the same rules as `codex-approval.ts` (shared fixture cases). Tests with fixture homes
for every check; mtimes unchanged. **Files:** new `hooks/native_collaboration_doctor.py` (imported by the runtime CLI),
new `hooks/test_doctor.py`.

### Task 5: `--expires-at` (D44)
Parser accepts ISO 8601 with offset or integer epoch seconds; others exit 2 naming the format. Tests; skill documents
it. **Files:** `hooks/session_delegation_control.py`, its tests, `skills/session-delegation/SKILL.md`.

### Task 6: Docs
README; collab skill (whoami, status/wait by id, bodyFile); collaboration-ops (doctor); interface rows 45, 51, 53, 65,
69, 91, 161, 165, gaps h, i, baseline findings 2, 6 (interface §14 numbering); checklist A1, A5, C8, D2, D16; `UPSTREAM.md`.

### Task 7: Live (coordinator told first)
Temporary `AGENT_RELAY_HOME`: runtime from this branch, `doctor` ok and with induced warnings; whoami from a Claude and a
Codex bridge; D16 file with metacharacters byte-identical; wait-by-id until a reply. Then one read-only `doctor` run on
the real environment (approved), mtimes of the real files checked before and after. No host config change.

### Checkpoint (gate): module review
