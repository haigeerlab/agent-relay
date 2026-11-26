# Spec: outbox-stale-filter

<!-- spec-guard: review pending -->

## Objective

Local ledger item QWRPD5B, from ecosystem-lead's inventory follow-up (mailbox #23165, 2026-11-26, the user's words 「按你的
建议做」). On 11-26 the user wanted to clear 13 old entries from their outbox — messages that expired before anyone read
them, or whose recipient name has since been retired — and found no way to. They stay in `bridge_outbox` forever, because
the default listing shows every direct message the recipient has not acknowledged, and an expired message or a retired
recipient never will.

This module gives a caller a way to leave those entries out, and has the collab skill use it when the user looks at what
they sent. Nothing is deleted and nothing is retired. Scope confirmed by the user in the owner session: 「说完了，确认插入」,
then 「确认写入」 for the capability-map row (default listing unchanged, opt-in parameter). ecosystem-lead gets this Spec
before review (interface change).

Readers: the user; the owner session (review, release, acceptance); ecosystem-lead (interface 2.13).

## What exists today (main 9b408ec, v0.10.0, interface 2.12, schema 8)

- `bridge_outbox` (`server.ts` 498–515, `views.ts` `outboxView`, `bridge-store.ts` `outbox()` 888–960) takes `agent`,
  `includeAcknowledged?`, `awaitingReply?`, `limit?`. Default: unacknowledged direct sends, newest first. Each entry carries
  `deliveryState` (`queued`, `sending`, `accepted`, `failed`, `unknown`, `expired`) and `recipient` (`active`, `retired`,
  `unknown`). The result carries `totalUnacknowledged`, `totalAwaitingReply`, `hasMore`.
- `awaitingReply: true` already leaves out failed, expired and retired-recipient requests (`OPEN_REQUEST`, D202).
- The runtime CLI `agent-relay outbox <agent>` (`cli-main.ts` 97) prints `outboxView` for the agent, field for field, and
  takes no flags (`docs/collaboration-interface.md` §2.4).
- The collab skill (`skills/collab/SKILL.md` 119) answers "what did I send that nobody answered" with `awaitingReply`; it
  has no instruction for "show my outbox".
- `bridge_agents` with `includeRetired: true` already lists retired names with `retiredAt` (since interface 2.4). The
  per-name lookup ecosystem-lead first asked for is dropped (#23172).
- **Who reads the default listing:** decision-inbox 0.0.37 reads its hub's `bridge_outbox` (with `includeAcknowledged`)
  and copies each entry's `deliveryState` into its own items (`__main__.py` 566, `items.py` 603), shown as 「投递 …」
  (`query.py` 339). If expired entries vanished from the default listing, its view would keep showing the last state it
  saw (for example `queued`) for a message that has expired. Hence the default stays as it is.

## Assumptions (confirmed by the user, 2026-11-26)

1. "Clear" means hide from the listing, not delete: history stays, and leaving the parameter off shows everything again.
2. The default `bridge_outbox` result does not change (decision-inbox depends on it); the filter is an opt-in parameter, so
   the interface goes up a minor version, 2.12 → 2.13.
3. No mailbox schema change (schema 8 stays). The two empty `orchestration_runs` / `orchestration_events` tables wait for
   the next release that changes the schema anyway.
4. Only the two kinds the user named are hidden: `deliveryState` `expired`, and a recipient whose name is retired.

## Decisions

- **D294 — `hideStale?: boolean` on `bridge_outbox`.** When true, the listing leaves out every entry whose
  `deliveryState` is `expired` or whose recipient is retired (`recipient: "retired"`). A recipient name that was retired
  and later reactivated is active again, and its entries show. An unknown recipient (`allowUnregistered`, never
  registered) is not hidden. Off or omitted: the result is byte-for-byte what 2.12 returns.
- **D295 — combines with the other inputs.** `hideStale` applies on top of `includeAcknowledged` (acknowledged entries to
  an expired or retired target are hidden too). With `awaitingReply` it changes nothing, since that view already leaves
  both kinds out. `limit` and `hasMore` count only the entries that are listed.
- **D296 — `hiddenStale` count.** With `hideStale: true` the result carries `hiddenStale: <n>`, the number of entries the
  filter left out, counted over everything the call matches (not only this page), so a caller can say "13 old messages hidden". Absent when
  `hideStale` is not set. `totalUnacknowledged` keeps its 2.12 meaning (every unacknowledged direct send) either way.
- **D297 — CLI flag.** `agent-relay outbox <agent> --hide-stale` passes `hideStale: true`; the output stays field for field
  the same as `bridge_outbox`. Any other flag is refused as today. Read-only, records no activity, as before.
- **D298 — collab skill.** When the user asks to see their outbox, what they sent, or what is still unhandled, call
  `bridge_outbox` with `hideStale: true` and report `hiddenStale` in one line ("另有 N 条已过期或收件方已退役，未列出"). When
  the user asks for everything, or about one of those old messages, call it without. `awaitingReply` questions stay as
  they are. Old messages are never acknowledged, retired or deleted on the user's behalf.

## Requirements

1. `bridge_outbox` input schema gains `hideStale` (optional boolean) with a short English description; output gains
   `hiddenStale` only when it is set (D294–D296).
2. The filter is done in the store's SQL, using the columns the query already joins (`m.delivery_state`, the recipient's
   `retired_at`); `hiddenStale` uses the same filter `includeAcknowledged` / acknowledgement condition as the listing.
3. `agent-relay outbox <agent> --hide-stale` (D297); `help` text lists the flag.
4. collab skill wording (D298), in Chinese like the rest of the skill.
5. `interface.json` → `2.13`; `docs/collaboration-interface.md`: the `bridge_outbox` row and the CLI `outbox` row describe
   `hideStale` / `hiddenStale` / `--hide-stale` "since interface 2.13", the header version note names 2.13.
6. `CHANGELOG.md` `[Unreleased]`: the change, "bridge 有改动，要 `upgrade --confirm` 升级运行时", schema 8 unchanged.
7. Tests (bridge, node test runner):
   - default listing unchanged for a mailbox holding active, expired, retired-recipient, reactivated and unknown-recipient
     messages (same entries and fields as without the parameter);
   - `hideStale: true` drops exactly the expired and retired-recipient entries, keeps reactivated and unknown, reports
     `hiddenStale`; combined with `includeAcknowledged` and with `limit` (paging still correct); no effect with
     `awaitingReply`;
   - CLI `--hide-stale` output equals the MCP result; an unknown flag is still refused;
   - `bridge/UPSTREAM.sha256` / `UPSTREAM.md` updated (`scripts/bridge-manifest.py`), hooks doc test for the skill wording
     if the existing doc tests cover collab.
8. `bash scripts/validate.sh` passes (full before merge, `--quick` while working).

## Boundaries

- **Always:** default `bridge_outbox` result unchanged; nothing deleted; English code and comments; Chinese commits / PR.
- **Ask first:** any change to the default listing; hiding `failed` entries as well; any schema change; anything under
  `.github/`.
- **Never:** automatic retirement of names (the 59 un-retired `mc-t` names stay until the user says so); acknowledging
  messages on the user's behalf; a delete or purge command; the per-name retirement lookup (#23172); dropping the
  orchestration tables in this module.

## Acceptance (owner session, after release and upgrade)

1. In a new session on the real host, `bridge_outbox` for `agent-relay-owner` without the parameter lists the same entries
   as before the upgrade (count compared with `totalUnacknowledged`).
2. With `hideStale: true`, the expired and retired-recipient entries are gone and `hiddenStale` matches the difference.
3. Asking the collab skill "看看我发出的消息" lists only live entries and states how many were hidden.
4. `~/.agent-relay/bin/agent-relay outbox agent-relay-owner --hide-stale` prints the same as step 2.

## Open questions

None. (Whether to hide `failed` entries too is left out on purpose: the user named only expired and retired.)
