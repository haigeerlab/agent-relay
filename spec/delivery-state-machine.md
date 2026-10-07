# Spec: delivery-state-machine

## Objective

Give every direct mailbox message an explicit delivery state, so that an ambiguous submission is visible and never
replayed, a message nobody fetched in time expires and is never acted on later, and an acknowledgement closes its
wake job. Woken sessions act on a message without asking, so a stale or duplicated delivery is the riskiest gap
(brief item 8). Also build the upgrade command specified in `bridge-vendoring` D26, because this is the first module
that changes the bridge.

Readers: the user; the round 1 coordinator (acceptance B4, B5, D12, D13 in the checklist); agents building
`durable-ordering`, `idempotency`, `identity-check`.

Sources: [interface](../docs/collaboration-interface.md) §5 rows 100–115, §3 rows 45–48 and 75, gaps a, b, c,
finding 5; [bridge-vendoring](bridge-vendoring.md) D26; the measurements below.

## What exists today (measured in the vendored bridge, 2026-10-07)

- `messages` has no state (`src/schema.ts:25-96`, `SCHEMA_VERSION = 2`). Delivery lives only in `wake_jobs`, one job
  per direct message to a wake-bound recipient (`UNIQUE(message_id, agent)`); broadcasts, self-sends and unbound
  recipients get no job (`wake-queue.ts:67-75`).
- Wake states `pending | sending | accepted | read | held | refused | unknown | cancelled | expired`
  (`wake-queue.ts:9`). `sending` with an expired 30 s lease becomes `unknown` and is never re-claimed
  (`:113-114`); a late receipt may still move `unknown`/`held` to a final state (`finish`, `:141-147`).
- Wake `expired` = only a `pending` job older than 1 h (offline) or 24 h (busy) (`:37-39`, `:119-124`). The
  message stays unread in the inbox and can be acted on later (gap c). No message TTL exists anywhere.
- `bridge_ack` only inserts into `acknowledgements` (`bridge-store.ts:461-478`); a job that is `accepted`/`read`/
  `unknown` stays so after ack (finding 5; `test/wake-queue.test.ts:79-83` pins it).
- `bridge_inbox` and `bridge_wait` show every unacknowledged delivered message; `bridge_outbox` shows the wake job
  state per send.
- Migrations are additive and old bridge processes keep running on the same file (`schema.ts:6-8`); `schema.test.ts`
  asserts 0.3-era raw INSERTs still work, so new columns must be nullable or defaulted.
- **The Python side pins `user_version == 2`:** `native_collaboration_retire.py:43` refuses, and
  `session_delegation_backend.py:79,131` return no route / no registration — a v3 mailbox would silently break
  retire and delegation result routing. `state_migration.py:40` lists non-final wake states.
- Upstream tests: 70 (`npm test`); delivery-related files `wake-queue`, `delivery`, `schema`, `lifecycle`.

## Assumptions

Confirmed by the user on 2026-10-07: evidence (late receipt, recipient fetch) may move `unknown` to `accepted`;
`interface.json` stays 1.0.

1. **Scope is direct messages.** Broadcasts (`to = "*"`) keep no delivery state; they are not woken today either.
2. **The message state is stored, not derived:** schema v3 adds nullable `messages.delivery_state`,
   `delivery_changed_at`, `read_at`, `expires_at`; rows written by an older process (NULL state) read as `queued`.
3. **States and rules** (interface §5 row 108, refined):
   - `queued` on send. `sending` when a wake is being submitted. `accepted` when the host confirms the wake **or**
     the recipient fetches the message (inbox/wait), so unbound recipients also reach a final state.
   - `failed` when the wake is refused for good (today `refused`); `held` (permission prompt) keeps the message
     `queued` with its reason.
   - `unknown` when a submission's outcome is not confirmed (today's stale `sending`, no receipt, failure after
     submit). **Never replayed.** It may still be resolved by evidence — a late host receipt or the recipient
     fetching it moves it to `accepted` — because that is observation, not a new delivery. Otherwise only an
     explicit user action changes it.
   - `expired` when a message is still `queued` at `expires_at`. Its wake job is cancelled, it is never pinged
     again, and `bridge_inbox` / `bridge_wait` hide it (only `bridge_inbox` can list it, with `includeExpired`). It stays in history
     (`bridge_thread`, `bridge_outbox`).
   - No transition out of `failed` or `expired` except an explicit user action (re-send is a new message).
4. **Finding 5:** `bridge_ack` moves the message's wake job to a new final state `acknowledged`.
5. **Python readers accept v2 and v3** (retire, delegation backend); `state_migration` learns the new non-final
   state set. `interface.json` stays 1.0 (user). **spec-guard is unaffected** (coordinator checked spec-guard main
   45ec482: nothing reads the mailbox; its probe only runs the declared `status` command) **provided
   `relay_status.py`'s output and its `ready` rule stay exactly as they are** — a requirement of this module.
6. **Upgrade command** exactly as D26 in `bridge-vendoring`, plus the schema: the mailbox backup is taken before
   the swap, and the new bridge migrates v2 → v3 on first open (its own `VACUUM INTO` pre-migration backup also
   runs). **Rollback after the migration:** the old `8f12c88` bridge does not refuse a v3 mailbox — it opens a newer
   schema in compatible mode (`server.ts:77`) and its rows leave the new columns NULL (read as `queued`) — but an
   older agent-relay plugin's Python hooks pin v2 and would stop retire and delegation result routing. So rolling
   back the runtime means rolling back the plugin too, or restoring the pre-upgrade mailbox backup (losing messages
   sent since); the upgrade output and README say so. Tested: v3 file opened by the vendored `8f12c88` code (in
   `bridge-vendoring`'s tree) works; old-hook behaviour on v3 documented. The real-runtime upgrade runs only with the
   user's go-ahead, after every session using the mailbox is closed, before integration round 2.

## Decisions

D27 (24 h default), D28 and D29 accepted on 2026-10-07.

- **D27 queue timeout default 24 h**, configurable per bridge by `BRIDGE_QUEUE_TIMEOUT_MS` (written into the host
  entry only if the user sets it) and per send by an optional `expiresInSeconds` (1 min … 7 days). Reasoning: the
  longest current wake window is 24 h (busy), and a request older than a day is more likely stale than wanted.
  Alternatives: 1 h (matches the offline window; too short for overnight work), 72 h.
- **D28 one transition function.** Every state change goes through one store method that checks the allowed
  transition table and records `delivery_changed_at`; adapters and sweeps call it instead of writing SQL.
- **D29 surfaced state.** `bridge_send` returns `deliveryState`; `bridge_outbox` and `bridge_wake_status` show it;
  `bridge_inbox` accepts `includeExpired` (history); `bridge_wait` never returns an expired message, because it hands messages to a session to act on and acknowledges them (narrowed at Task 5). Tool descriptions and the README say exactly-once is not
  promised (interface row 114).

## Requirements

1. Schema v3 additive migration with the four nullable columns; old-process INSERTs still work; v2 → v3 backup
   before migration (existing `beforeUpgrade`).
2. The transition table of assumption 3 enforced in one place (D28); illegal transitions refused and tested.
3. `unknown` is never re-claimed or re-sent; tests for stale lease, no receipt, failure after submit, late receipt.
4. Expiry: a `queued` message past `expires_at` becomes `expired`, its job cancelled, hidden from inbox/wait by
   default, never pinged; a message already `accepted` never expires.
5. Ack closes the wake job as `acknowledged` (finding 5); the pinned upstream test is updated deliberately.
6. Python hooks accept v2 and v3; `state_migration` state lists updated; tests for both versions. `relay_status.py`
   output and `ready` rule unchanged (pinned by its existing tests).
7. `upgrade --confirm` per D26, with tests (refuses while a server runs, backup first, mailbox/data moved, counts
   verified, previous directory kept, rollback on failure).
8. `UPSTREAM.md` "agent-relay changes" lists these changes; `UPSTREAM.sha256` updated; README / interface §3, §5
   updated; checklist B4, B5, D12, D13 target wording checked.

## Commands

```bash
/bin/bash scripts/validate.sh
(cd plugins/agent-relay/bridge && npm ci && npm run check)   # typecheck, build, upstream + new TS tests
```

## Testing strategy

- TS (node test runner, in the bridge): transition table, each adapter result, sweeps, expiry, ack, inbox filters,
  schema v2→v3 and old-process compatibility; run with `npm run check` in a temporary copy (sealed HOME/TMPDIR).
- Python: hooks accept v3 fixtures; upgrade command with a fake runtime; `validate.sh` gains a step that runs the
  bridge's `npm run check` only when `node_modules` is present (decided in the plan).
- Live (coordinator's environment, user go-ahead): B4/B5 states, D12 (close target during delivery → `unknown`,
  never replayed), D13 (short timeout → `expired`, hidden, never delivered), and the real-runtime upgrade.

## Boundaries

- Always: additive migration; never replay `unknown`; keep history.
- Ask first: changing `interface.json` version; running the upgrade on the real runtime; any host config change.
- Never: delete messages; push without approval.

## Success criteria

1. TS and Python suites green; transition and expiry tests cover every row of assumption 3.
2. Upgrade command tested; a v2 mailbox migrates with a backup and counts intact.
3. Live B4, B5, D12, D13 pass against the target column.

## Open questions

None.
