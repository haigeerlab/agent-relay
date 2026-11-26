# Plan: outbox-stale-filter

<!-- spec-guard: review pending -->

Based on [`spec/outbox-stale-filter.md`](../../spec/outbox-stale-filter.md) (approved by the user on 2026-11-26:
assumptions 1–5, D294–D298). Built on branch `claude/outbox-stale-filter` from main 9b408ec; one PR. Codex implements
each task (`/delegate:run --write`); the owner accepts (diff, focused tests, `bash scripts/validate.sh --quick`, full run
before the PR). Nothing here touches the main clone, the hosts, the runtime or the mailbox on this Mac.

Found while planning (read-only, main 9b408ec):
- `bridge/src/bridge-store.ts` `outbox()` (L888–960) builds one `filter` string: `OPEN_REQUEST` for `awaitingReply`,
  otherwise `""` or `AND a.acked_at IS NULL`; it already joins `agents r` (`r.retired_at AS recipient_retired`) and reads
  `m.delivery_state`. The stale condition goes into the same `filter`; `hiddenStale` is one more `COUNT(*)` with the
  listing's acknowledgement condition plus the inverted stale condition.
- `bridge/src/views.ts` `outboxView` passes options through; `server.ts` `bridge_outbox` (L498–515) holds the input schema
  and the tool description; `cli-main.ts` L97 calls `outboxView` with only `agent` (no change, D297).
- Existing tests that read expired entries from the default listing, e.g. `bridge/test/script-access.test.ts:54`; others
  show up when the default changes (`delivery-expiry`, `delivery-state`, `script-views`, `script-cli`, `mcp-integration`).
- Interface version pinned in `hooks/test_packaging.py:41`; history line in `hooks/relay_status.py:5`.
- collab skill: `skills/collab/SKILL.md` L119 (the `awaitingReply` paragraph).

## Task List

### Task 1: default stale filter, `includeStale`, `hiddenStale` (D294–D297; requirements 1, 2, 6)
Red first, new `bridge/test/outbox-stale.test.ts` on a mailbox holding, from one sender: an active message, an expired
one, one to a retired name, one to a name retired then reactivated, one to an unknown recipient (`allowUnregistered`):
(a) default lists active, reactivated and unknown only, `hiddenStale: 2`;
(b) `includeAcknowledged: true` with one acknowledged message to the retired name: still hidden, counted;
(c) `limit: 1`: one entry, `hasMore` true, `hiddenStale` still 2 (whole match, not the page);
(d) `includeStale: true`: all five, no `hiddenStale`, entries field for field as without the filter;
(e) `awaitingReply: true`, with and without `includeStale`: same result as before, no `hiddenStale`;
(f) no stale message: no `hiddenStale`;
(g) the built CLI `outbox <sender>` prints the same JSON as `outboxView` (in `script-cli.test.ts`).
Green: `bridge-store.ts` filter and count; `views.ts` / `server.ts` input `includeStale` with an English description, tool
description says stale entries are left out by default and how to list them. Existing tests that expected stale entries
in the default listing pass `includeStale: true`, assertions unchanged. `python3 scripts/bridge-manifest.py`.

### Task 2: interface 2.13, skill and docs (D296, D298; requirements 3–5)
Red first, new `hooks/test_outbox_stale_docs.py`: `interface.json` is 2.13; the interface doc's `bridge_outbox` row names
`includeStale`, `hiddenStale` and 2.13; the CLI `outbox` row says it follows the same default; the collab skill names
`hiddenStale` and `includeStale` with D298's sentence; CHANGELOG `[Unreleased]` names the module. Green: `interface.json`,
`hooks/test_packaging.py` pin, `hooks/relay_status.py` history (`2.13 since outbox-stale-filter D294`), the docs, the
skill paragraph, CHANGELOG (default outbox changed, `upgrade --confirm`, schema 8 unchanged), `bridge/UPSTREAM.md` row.

### Checkpoint (report): owner acceptance of Tasks 1–2
Diff read in full; `bash scripts/validate.sh` full run passes; same-vendor review of the branch
(`/delegate:review --backend claude-code`, base 9b408ec, with the Spec) and its blocking findings fixed; a grep of the
diff finds no real session id or consumer project name. Results go into `todo.md`, then on to the gate.

### Checkpoint (gate): push and open the PR
Shown to the user: what changed, test counts, review result. On the user's yes: push, open the PR (Chinese title and body),
ask 「PR #N 已开，CI 正在跑，可以合并吗」 at once (F3); merge only after the user's 「合并」.

## Risks and mitigations

- **A 2.12 caller sees fewer entries.** Only the retired decision-inbox read the default listing; `includeStale` restores
  it; the CHANGELOG and interface doc say so.
- **`hiddenStale` drifting from the listing.** It is computed by the same SQL condition, tested with paging (c).
- **Hidden messages forgotten.** Nothing is deleted; the skill always reports `hiddenStale` when present.
- **Codex's sandbox cannot run every test.** The owner runs `validate.sh` locally for each task.

## Open questions

None.
