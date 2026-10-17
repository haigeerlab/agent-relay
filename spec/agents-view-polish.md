# Spec: agents-view-polish

## Objective

Only module of 0.8.1 (bridge, docs). The usage observation of 2026-10-17 left three low-priority items (`bridge_agents
{includeRetired}` too large, two read rules that disagree, presence that cannot tell idle from busy), and the 0.8.0
acceptance measured a fourth (`bridge_agents` taking more than ten seconds). The user decided on 2026-10-17 to handle
them as one low-priority module ("假设通过，第 5 条选 (a)").

Readers: the user; the round-2 coordinator and the usage observer (review, re-check after release); the Spec Guard owner
(interface 2.4 is within its accepted `>=1.0,<3.0`).

## What exists today (main 7d22e06, v0.8.0)

- **A.** `bridge_agents` takes only `includeRetired`. With it, every identity comes back in full (capabilities, host,
  wake, lastPing, waiting, owesReplies …), ordered by registration time then name, with no paging and no budget. The
  real mailbox holds 189 identities, 167 retired; the observer measured about 98 KB, past what hosts show inline.
- **B.** `bridge_inbox` lets anyone read any identity's messages in full (`readRecorded: false` for a reader that is not
  the identity; inbox-read-receipt D99, D100), and its `messageId` reads any message by naming its recipient.
  `bridge_wake_status {messageId}` refuses everyone but the sender and the recipient (`server.ts` `statusFor`,
  ops-commands). The restriction protects nothing the inbox does not already show.
- **C.** `claudePresence` maps Claude Code's registry status: `waiting` → `waiting-approval` / `waiting-input`,
  anything else → `running` (presence-and-approval D146). Claude Code writes `busy` and `idle`; both read `running`.
- **D.** `bridge_agents` asks the ChatGPT app once per active Codex identity, in parallel, with the IPC default of
  **10 s**; a task the app has not loaded answers nothing, so one such task makes the listing take ten seconds or more
  (measured in the 0.8.0 acceptance; 10 active Codex identities today). The awaiting-reply view already caps the same
  question at 2 s (`AWAITING_PRESENCE_TIMEOUT_MS`, D203).

## Assumptions (accepted by the user 2026-10-17)

1. **One module**, bridge and docs only. Mailbox schema 7 unchanged; interface 2.3 → **2.4** (additions only); released
   as **0.8.1**.
2. **A: `bridge_agents` pages like `bridge_inbox`.** New `maxChars?` (default 48 000, as the inbox) and `afterName?`; the
   result carries `hasMore` and, when true, `nextAfterName`. **Retired entries are compact**: `name`, `retiredAt`,
   `retiredBy`, `retireNote`, `unread`, `lastActivity`, `wake`, and `waiting` when present — every field the interface
   document promises stays; capabilities, host, lastPing and the like are left out. Without `includeRetired` the agents
   listed and their fields are as today.
3. **B: anyone may ask `bridge_wake_status {messageId}`**, matching `bridge_inbox`, under identity-check's threat model
   ("one user, one Mac": stop mistakes, not malice). A widening, so an addition; reading the status records nothing.
   Tightening `bridge_inbox` instead is not done (a breaking change, and upper layers read other inboxes).
4. **C: Claude presence gains `activity`**: `"busy"` or `"idle"`, only when `state` is `running`, taken from the registry
   status. `state` keeps its values and meaning. Codex presence has no reliable busy signal and gets no `activity`.
5. **D: `bridge_agents` waits at most 2 s for the ChatGPT app**, the awaiting view's constant; a task that does not
   answer in time is still `not-loaded` (user's choice (a): loaded tasks answer in milliseconds, host-differences H2).
   **`bridge_send` gets the same cap** for its recipient presence check and its notice-location lookup (added by the
   user on 2026-10-17 when approving this spec: a send to a task that is not open also waited ten seconds).
6. **Not in scope**: the meaning of `running`, Codex busy tracking, schema changes, deleting retired identities.
7. **Verification**: red first for each; D against a fake ChatGPT socket that never answers, with a time bound; on the
   real host the coordinator checks `bridge_agents` returns within 3 s and `includeRetired` pages to the end.

## Decisions

- **D223 `bridge_agents` pages and keeps retired entries short (A).** `maxChars` budget in the inbox's units
  (`textCost`, 1 000 … 400 000, default 48 000) and `afterName` cursor, continuing in the listing's own order
  (registration time, then name) after the named identity; an unknown `afterName` is refused. A page always holds at
  least one entry. `count` is the entries on this page; `hasMore` is always present; `nextAfterName` only when
  `hasMore`. Retired entries carry only the fields in assumption 2; presence is never looked up for them (D176 stays).
- **D224 message status is open to every caller (B).** `statusFor` drops the sender/recipient check; a nonexistent id
  still says `No message #N.` The `bridge_wake_status` description says so. Interface table row updated.
- **D225 Claude presence says whether a running session is in a turn (C).** `activity: "busy" | "idle"` on a Claude
  presence whose `state` is `running` and whose registry status is exactly `busy` or `idle`; absent otherwise (other or
  missing status, every other state, every Codex presence). Consumers treat it as optional.
- **D226 the ChatGPT app is asked for at most 2 s (D).** `codexOwner(…, { responseTimeoutMs:
  AWAITING_PRESENCE_TIMEOUT_MS })` in `bridge_agents`, in `bridge_send`'s recipient presence check (`presenceOf`, used
  by `checkRecipient`) and in its notice-location lookup; silence after connecting stays `not-loaded` with the D200
  detail. The awaiting view keeps its own mapping (silence → `unknown`, D203).
- **D227 interface 2.4, plugins in any order.** `interface.json` 2.4; the interface document lists `maxChars`,
  `afterName`, `hasMore`, `nextAfterName`, the compact retired entry, the open message status and `activity`. No schema
  change, so plugin and runtime may be updated in either order; the CHANGELOG says so, and that the runtime needs
  `upgrade --confirm`.

## Requirements

1. Red first, `bridge/test/agents-view.test.ts` (new):
   - 30 retired identities with long notes and capabilities: `includeRetired` with a small `maxChars` returns pages with
     `hasMore`/`nextAfterName` until the last page, every identity exactly once, in registration order; retired entries
     have only the compact fields; an unknown `afterName` is refused;
   - without `includeRetired` the active entries keep every field they had;
   - `bridge_wake_status {messageId}` from a session that is neither sender nor recipient returns the status (MCP test);
   - presence: registry `busy` → `running` + `activity: busy`; `idle` → `activity: idle`; `waiting` and unknown status →
     no `activity`; Codex → no `activity`;
   - `bridge_agents` with one Codex identity whose app socket accepts and never answers returns within 3 s and reports
     that identity `not-loaded`; `bridge_send` to that identity returns within 3 s with its usual not-loaded warning.
2. `server.ts`: parameters, descriptions, `statusFor`, the 2 s cap; `presence.ts` `activity`.
3. Interface 2.4: `interface.json`, `test_packaging`, `relay_status.py` docstring, `docs/collaboration-interface.md`.
4. Bridge bookkeeping (D24): `UPSTREAM.md` row and manifest; `bridge/CHANGELOG.md` 0.8.1; CHANGELOG `[Unreleased]`.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Always: tests first; additions only; every promised field stays.
- Ask first: changing presence `state` values; any field removed from active entries; tightening any read.
- Never: read message bodies to build a listing; look up presence for retired identities.

## Acceptance (after 0.8.1)

- On the real host: `bridge_agents`, and `bridge_send` to a Codex task that is not open, return within 3 s; `includeRetired` with the
  default budget pages through all identities; a running Claude session shows `activity` busy during a turn and idle
  after; a third session reads another pair's message status by id.

## Open questions

- None.
