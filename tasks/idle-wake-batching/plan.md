# Plan: idle-wake-batching

<!-- spec-guard: review pending -->

Based on [`spec/idle-wake-batching.md`](../../spec/idle-wake-batching.md) (approved by the user on 2026-11-26,
「批准，确认插入」: assumptions 1–8, D299–D308; commit 6d9d718). Local ledger item PH9ME24. Built on branch
`claude/idle-wake-batching` from main 819e2f8; one PR. Codex implements each task (`/delegate:run --write`); the owner
accepts (diff, focused tests, `bash scripts/validate.sh --quick`, full run before the PR). Nothing here touches the main
clone, the hosts, the runtime or the mailbox on this Mac.

Found while planning (read-only, main 819e2f8):
- `bridge/src/bridge-store.ts` L525 `if (input.wake !== false) this.wakes.enqueue(message)`; `SendInput.wake?: boolean`
  (L72). `wake-queue.ts` `enqueue` (L170) inserts `(message_id, agent, target, retry_at, created_at)`.
- `wake-queue.ts`: `CLAIMABLE` (older `pending`/`sending` blocks), `PENDING_EXPIRED` (1 h unless `busy`), `claim` (L281),
  `finish` (L334), `waiting` (L351), `health` (L391). `PendingReason = "busy" | "offline" | "unreachable"`.
- `wake-dispatcher.ts` `drain` claims and dispatches; `checkApprovals` already reads the Claude registry every 30 s
  (`claudeSessions` injectable); `claudePresence` (`presence.ts`) gives `state`, `activity`, `since`.
- `schema.ts` migrations end at v8 (L182, `addColumn` on `agents`); `SCHEMA_VERSION = 8` (L10).
- CLI: `cli-logic.ts` L82 default `wake: true`, L96 `--no-wake`; `cli-main.ts` `send` (L207) calls `sendMessage`.
- Interface version pinned in `hooks/test_packaging.py`; history line in `hooks/relay_status.py:5`.
- Tests to extend: `wake-queue.test.ts`, `delivery-wake.test.ts`, `rewake.test.ts`, `schema.test.ts`, `cli.test.ts`,
  `script-cli.test.ts`.

## Task List

### Task 1: schema 9 and explicit wake (D300, D307; requirements 1, 4 CLI part)
Red first: `schema.test.ts` — an 8 → 9 upgrade adds `wake_jobs.explicit_wake` (default 0) and keeps existing rows;
store test — `wake: true` records 1, omitted records 0, `wake: false` creates no job; `cli.test.ts` — `--wake` parses to
an explicit wake, `--wake --no-wake` is refused with a clear message, usage text lists `--wake`.
Green: v9 migration, `SCHEMA_VERSION = 9`; `SendInput` keeps the three-way `wake`; `enqueue` writes `explicit_wake`;
`WakeJob.explicitWake`; CLI parser and usage. No behaviour change yet. `python3 scripts/bridge-manifest.py`.

### Task 2: hold and release in the queue and dispatcher (D299, D301–D304, D306; requirements 2, 3)
Red first, new `bridge/test/idle-hold.test.ts` with an injected registry (`claudeSessions`) and clock:
(a) held: idle ≥ threshold, no `expectsReply`, omitted wake → `pending`/`idle`, detail as D301, nothing dispatched,
message `queued`; (b) not held, one case each: `expectsReply`, explicit wake, Codex target, `busy`, `waiting`, idle below
threshold, no `statusUpdatedAt`, registry unreadable, session not found, threshold 0, under 1 h to `expires_at`;
(c) a held job does not block a later job for the same recipient, and dispatching that later ping first releases the held
ones (D303 b); (d) release on `busy`, on newer `statusUpdatedAt`, on stop (then pending `offline`), near expiry, on start
with threshold 0; a released job is never held again; (e) a held job survives past the 1 h pending window, is cancelled
when its message expires, closed when the message is acknowledged; (f) no desktop notice and no `bridge` notice for a
hold; (g) `BRIDGE_IDLE_HOLD_MS` parsing (D304).
Green: `PendingReason` adds `"idle"`; `CLAIMABLE` / `PENDING_EXPIRED` changes; `WakeQueue.holdIdle`, `releaseHeld`,
`heldAgents`, near-expiry query; dispatcher check before `dispatch`, release in the 30 s tick and before a non-held ping,
start-time release; `idleHoldMs(env)`. Existing `wake-queue`, `delivery-wake`, `rewake` tests stay green unchanged.
Manifest rerun.

### Task 3: what the sender sees (D305; requirements 4 warning, 5)
Red first: `bridge_send` to an idle-past-threshold Claude recipient without `expectsReply` carries the D305 warning; no
warning with `expectsReply`, explicit wake, or an active recipient; `bridge_outbox` and `bridge_wake_status` show
`pendingReason: "idle"` and the held detail; CLI `outbox` matches the MCP view.
Green: send-time check sharing Task 2's predicate; tool descriptions for `bridge_send` (`wake`), `bridge_outbox`,
`bridge_wake_status`. Manifest rerun.

### Task 4: interface 2.14, skills and docs (D308; requirements 6–8)
Red first, new `hooks/test_idle_hold_docs.py`: `interface.json` is 2.14; the interface doc rows for `bridge_send`,
`bridge_outbox` / `bridge_wake_status`, CLI `send --wake` and schema 9 name 2.14; collab and session-routing skills carry
D308's wording; README 唤醒与送达 names `BRIDGE_IDLE_HOLD_MS`; CHANGELOG `[Unreleased]` names the module, schema 8 → 9
and `upgrade --confirm`.
Green: `interface.json`, `hooks/test_packaging.py` pin, `hooks/relay_status.py` history (`2.14 since idle-wake-batching
D305`), docs, skills, README, CHANGELOG, `bridge/UPSTREAM.md` row, manifest rerun.

### Checkpoint (report): owner acceptance of Tasks 1–4
Diff read in full; `bash scripts/validate.sh` full run passes; same-vendor review of the branch
(`/delegate:review --backend claude-code`, base 819e2f8, with the Spec) and its blocking findings fixed; a grep of the
diff finds no real session id or consumer project name. Results go into `todo.md`, then on to the gate.

### Checkpoint (gate): push and open the PR
Shown to the user: what changed, test counts, review result. On the user's yes: push, open the PR (Chinese title and body),
ask 「PR #N 已开，CI 正在跑，可以合并吗」 at once (F3); merge only after the user's 「合并」. Release (0.11.0), upgrade and
acceptance AC1–AC4 follow `RELEASING.md` and are asked for separately; ecosystem-lead is told on release.

## Risks and mitigations

- **A held message never delivered.** Every held job ends by release (activity, next ping, near expiry, threshold 0), by
  its message's own expiry, or by acknowledgement; each path has a test (Task 2 d, e).
- **A held job blocking an urgent one.** `CLAIMABLE` leaves held jobs out; tested (Task 2 c).
- **Wrong idle reading holds a live session.** Anything not clearly `idle` past the threshold pings as today; one test per
  unknown case (Task 2 b). Release is checked every 30 s, so a session that wakes gets its pings within about 30 s of its
  turn ending.
- **Mixed versions during upgrade.** An old bridge never claims a held job (`retry_at` in the future) and may expire it
  after 1 h; the message stays unread in the inbox (Spec, Mixed versions).
- **Schema 9 cannot be read by 0.10.x.** As for every schema bump: rollback goes through `upgrade-recovery`; the
  CHANGELOG says so.
- **Codex's sandbox cannot run every test.** The owner runs `validate.sh` locally for each task.

## Open questions

None.
