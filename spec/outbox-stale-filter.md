# Spec: outbox-stale-filter

<!-- spec-guard: review approved 426fc26832eb -->

## Objective

Local ledger item QWRPD5B, from ecosystem-lead's inventory follow-up (mailbox #23165, 2026-11-26, the user's words 「按你的
建议做」). On 11-26 the user wanted to clear 13 old entries from their outbox — messages that expired before anyone read
them, or whose recipient name has since been retired — and found no way to. They stay in `bridge_outbox` forever, because
the default listing shows every direct message the recipient has not acknowledged, and an expired message or a retired
recipient never will.

This module leaves those entries out of the default listing, says how many were left out, and lets a caller ask for them
back. Nothing is deleted and nothing is retired. Scope set by the user in the owner session: 「说完了，确认插入」, then, after
ecosystem-lead's review of the first draft (#23183), 「A：默认隐藏，不加 CLI」.

Readers: the user; the owner session (review, release, acceptance); ecosystem-lead (interface 2.13).

## What exists today (main 9b408ec, v0.10.0, interface 2.12, schema 8)

- `bridge_outbox` (`server.ts` 498–515, `views.ts` `outboxView`, `bridge-store.ts` `outbox()` 888–960) takes `agent`,
  `includeAcknowledged?`, `awaitingReply?`, `limit?`. Default: unacknowledged direct sends, newest first. Each entry carries
  `deliveryState` (`queued`, `sending`, `accepted`, `failed`, `unknown`, `expired`) and `recipient` (`active`, `retired`,
  `unknown`). The result carries `totalUnacknowledged`, `totalAwaitingReply`, `hasMore`.
- `awaitingReply: true` already leaves out failed, expired and retired-recipient requests (`OPEN_REQUEST`, D202).
- The runtime CLI `agent-relay outbox <agent>` (`cli-main.ts` 97) prints `outboxView` for the agent, field for field.
- The collab skill (`skills/collab/SKILL.md` 119) answers "what did I send that nobody answered" with `awaitingReply`; it
  has no instruction for "show my outbox".
- `bridge_agents` with `includeRetired: true` already lists retired names with `retiredAt` (since interface 2.4). The
  per-name lookup ecosystem-lead first asked for is dropped (#23172).
- The only plugin seen reading the default listing is decision-inbox 0.0.37 (`__main__.py` 566). The user retired it on
  11-19 (「按没有这个插件对待」, plugin-ecosystem `ECOSYSTEM-MAP.md` lines 13 and 22), so it does not hold the default back.

## Assumptions (confirmed by the user, 2026-11-26)

1. "Clear" means hide from the listing, not delete: history stays, and `includeStale: true` shows everything again.
2. The default listing changes (stale entries left out). Fields are only added and `awaitingReply` already filters the same
   way, so the interface goes up a minor version, 2.12 → 2.13; a 2.12 caller simply sees fewer old entries.
3. No mailbox schema change (schema 8 stays). The two empty `orchestration_runs` / `orchestration_events` tables wait for
   the next release that changes the schema anyway.
4. Only the two kinds the user named are stale: `deliveryState` `expired`, and a recipient whose name is retired.
5. The runtime CLI gets nothing new (ecosystem-lead #23183: the script CLI has no callers; the user agreed).

## Decisions

- **D294 — stale entries hidden by default.** `bridge_outbox` leaves out every entry whose `deliveryState` is `expired` or
  whose recipient is retired (`recipient: "retired"`). A name that was retired and later reactivated is active again, and
  its entries show. An unknown recipient (`allowUnregistered`, never registered) is not hidden.
- **D295 — `includeStale?: boolean` brings them back.** True lists them as 2.12 did. The filter applies on top of
  `includeAcknowledged` (acknowledged entries to an expired or retired target are hidden too, unless `includeStale`). With
  `awaitingReply` neither the filter nor `includeStale` changes anything, since that view already leaves both kinds out.
  `limit` and `hasMore` count only the entries that are listed.
- **D296 — `hiddenStale` count.** When the filter left out at least one entry, the result carries `hiddenStale: <n>`,
  counted over everything the call matches (not only this page); absent when nothing was hidden, with `includeStale`, and
  with `awaitingReply`. `totalUnacknowledged` keeps its 2.12 meaning (every unacknowledged direct send) either way.
- **D297 — runtime CLI unchanged in input.** `agent-relay outbox <agent>` takes no new flag. It prints `outboxView`, so its
  output follows the new default (stale entries hidden, `hiddenStale` when any were).
- **D298 — collab skill.** When the user asks to see their outbox, what they sent, or what is still unhandled, call
  `bridge_outbox` as usual and, when `hiddenStale` is present, say in one line 「另有 N 条已过期或收件方已退役，未列出」. When the
  user asks for everything, or about one of those old messages, call it with `includeStale: true`. `awaitingReply`
  questions stay as they are. Old messages are never acknowledged, retired or deleted on the user's behalf.

## Requirements

1. `bridge_outbox` input schema gains `includeStale` (optional boolean) with a short English description; the tool
   description says stale entries are left out by default; output gains `hiddenStale` as in D296.
2. The filter is done in the store's SQL, using the columns the query already joins (`m.delivery_state`, the recipient's
   `retired_at`); `hiddenStale` uses the same acknowledgement condition as the listing.
3. collab skill wording (D298), in Chinese like the rest of the skill.
4. `interface.json` → `2.13`; `docs/collaboration-interface.md`: the `bridge_outbox` row describes the default filter,
   `includeStale` and `hiddenStale` "since interface 2.13"; the CLI `outbox` row notes it follows the same default; the
   header version note names 2.13.
5. `CHANGELOG.md` `[Unreleased]`: the change, that the default outbox no longer lists stale entries, "bridge 有改动，要
   `upgrade --confirm` 升级运行时", schema 8 unchanged.
6. Tests (bridge, node test runner), on a mailbox holding active, expired, retired-recipient, reactivated and
   unknown-recipient messages:
   - default drops exactly the expired and retired-recipient entries, keeps reactivated and unknown, reports
     `hiddenStale`; combined with `includeAcknowledged` and with `limit` (paging and `hasMore` still correct);
   - `includeStale: true` returns the same entries and fields as 2.12 did, no `hiddenStale`;
   - `awaitingReply` result unchanged, no `hiddenStale`;
   - existing tests that expected stale entries in the default listing are updated to pass `includeStale`, keeping their
     assertions strict;
   - CLI `outbox` output equals the MCP result for the same agent;
   - `bridge/UPSTREAM.sha256` / `UPSTREAM.md` updated (`scripts/bridge-manifest.py`).
7. `bash scripts/validate.sh` passes (full before merge, `--quick` while working).

## Boundaries

- **Always:** nothing deleted; `includeStale` restores the 2.12 listing; English code and comments; Chinese commits / PR.
- **Ask first:** hiding `failed` entries as well; any schema change; anything under `.github/`.
- **Never:** automatic retirement of names (the 59 un-retired `mc-t` names stay until the user says so); acknowledging
  messages on the user's behalf; a delete or purge command; a new runtime CLI flag; the per-name retirement lookup
  (#23172); dropping the orchestration tables in this module.

## Acceptance (owner session, after release and upgrade)

1. AC1: in a new session on the real host, `bridge_outbox` for `agent-relay-owner` lists no expired or retired-recipient
   entry, and `hiddenStale` equals the number left out (compared with the same call with `includeStale: true`).
2. AC2: with `includeStale: true` the listing has the same entries as before the upgrade.
3. AC3: asking the collab skill 「看看我发出的消息」 lists only live entries and states how many were hidden.

## Open questions

None. (Whether to hide `failed` entries too is left out on purpose: the user named only expired and retired.)
