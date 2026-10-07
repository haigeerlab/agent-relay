# Plan: cleanup-gaps

Based on [`spec/cleanup-gaps.md`](../../spec/cleanup-gaps.md) (accepted by the user on 2026-10-08: assumptions 1–5,
D59–D63, D61 = A). Branch `claude/cleanup-gaps` from main 5d12346. Red → green, one commit per task.

## Task List

### Task 1: Retire follows the bridge's unread rule and names what blocks (D59)
`identity_state` excludes `delivery_state = 'expired'` exactly like `UNREAD_FOR` and returns the blocking ids with
their delivery state; the refusal lists at most 10 (`id state`, then "and N more"), never bodies.
Tests in `hooks/test_native_collaboration_retire.py`: one expired unacknowledged message → retired; one `accepted` →
refused naming its id and `accepted`; 12 blocking → 10 ids + "and 2 more"; no body text in the output.
**Files:** `hooks/native_collaboration_retire.py`, its test.

### Task 2: Cancel closes a never-turned, host-rejected Codex record (D60)
In `CodexAdapter.cancel`'s `RpcRejected` branch: when the row is `unknown` with no `host_session_ref` and no
`last_turn_ref`, advance to `cancelled` (`host-cancelled`) and return `cancelled` with
`prerequisite = host-thread-absent`; otherwise unchanged. Tests in `hooks/test_session_delegation_codex.py` with the
existing fake app-server returning -32600 on `thread/archive`: the never-turned record → `cancelled`; a record with a
`last_turn_ref` → still `unknown`; `creating` and completed records as today. Check the controller's public result
passes the prerequisite through.
**Files:** `hooks/session_delegation_codex.py`, its test.

### Task 3: bridge_register refuses a retired name unless `reactivate: true` (D61 A)
`server.ts`: new `reactivate` input; an existing retired row without it → error naming the retired state and "pass
reactivate: true only after the user agrees" (checked before any wake bind or write); with it → registered, result
`reactivated: true` and a note with the earlier `retiredAt`; active names unchanged. Rewrite
`lifecycle.test.ts` "reactivates retired agents" for the store (store.register stays the primitive); MCP tests in
`mcp-integration.test.ts`: plain register, `takeover: true`, and `reactivate: true` on a retired name; active name
with `reactivate: true`. Texts: `bridge_register` and `bridge_retire` descriptions, `INSTRUCTIONS` (refused retired
name → ask the user or choose a new name), `bridge-store.ts` comment, `cli.ts` prune output, `bridge/README.md`.
`UPSTREAM.md` change row; `python3 -B scripts/bridge-manifest.py` rewrites `UPSTREAM.sha256`.
**Files:** `bridge/src/server.ts`, `bridge/src/bridge-store.ts`, `bridge/src/cli.ts`, `bridge/README.md`,
`bridge/test/*.test.ts`, `bridge/UPSTREAM.md`, `bridge/UPSTREAM.sha256`.

### Task 4: Codex follow-up to a retired delegated identity is held (D63)
`continue_turn` checks the mailbox read-only before `thread/resume` (via the backend, like
`native_registration_probe`); `<friendly>-<thread[:8]>` present and retired → `held`, `identity-retired`, no host
request. Tests: retired → held, fake app-server sees no request; active → follow-up as today; mailbox unreadable →
behaviour as today (no new refusal).
**Files:** `hooks/session_delegation_codex.py` (+ `session_delegation_backend.py` if the probe lives there), tests.

### Task 5: Interface and docs (D62)
`interface.json` → `"1.1"` and every test/check that pins it; `docs/collaboration-interface.md` rows
(`bridge_register`, retire, delegation `identity-retired`); `references/collaboration-runtime.md` retirement text;
CHANGELOG `Unreleased`: the three gaps, D63, interface 1.1, and that the bridge change needs
`upgrade --confirm` with sessions closed. `scripts/acceptance/preflight.py` prints whether the runtime's bridge is
current or older than this checkout's (from `status`'s `bridge.current`; approved by the user 2026-10-08), with a test.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 6: Live (temporary `AGENT_RELAY_HOME`/HOME, coordinator told first)
**Upgrade path first (spec assumption 4).** In a temporary root, install a runtime from the v0.2.0 tag (an export of
5d12346) and leave history: a few messages and one retired identity. With this branch: `doctor` → `runtime` warn
"bridge is older than this plugin's" (already in doctor; confirms a plugin-only update is noticed), then
`upgrade --confirm`. Check: mailbox message count kept and every pre-upgrade message byte-identical (id, body,
state), schema still 5; register of the retired name refused, `reactivate: true` → `reactivated`; `doctor` → `ok`.
**Then the gaps.** Gap 1: a message with `expiresInSeconds: 60` left to expire → retire `retired`; an `accepted`
unacknowledged message → refusal names its id. Gap 3 as above. Gap 2 and D63 stay with the fake app-server (Task 2/4
tests); the two real records are the coordinator's check after merge.

### Checkpoint (gate): module review
