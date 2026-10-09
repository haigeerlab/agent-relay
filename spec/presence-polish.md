# Spec: presence-polish

## Objective

Second module of 0.6.1: the bridge findings of the round-2 coordinator's post-release review of 0.6.0 (items 5a, 5b,
5e, 5k), accepted by the user on 2026-10-09. All are small; together they make presence and the approval notice say
what is true and stop doing work nobody asked for.

Readers: the user; the round-2 coordinator.

## What exists today (main 835304b, v0.6.0)

- **5a.** The approval notice is de-duplicated by `approval-<session>-<presence.since ?? "unknown">`
  (`wake-dispatcher.ts:123`). `since` comes from `statusUpdatedAt`; when Claude Code does not write it, every later
  waiting episode of that session has the same key, so after the first notice it is never notified again.
- **5b.** `claudeWaiting` (`bridge-store.ts:749`) takes every Claude-hosted agent with an unhandled message, bound to
  wake or not, while presence-and-approval assumption 4 limits background reading. And `claudeSessions`
  (`claude-wake.ts:42`) returns `[]` when the registry directory cannot be read, so `claudePresence` says `stopped`
  instead of `unknown`.
- **5e.** `bridge_inbox` with `messageId` and a `bodyOffset` past the end returns an empty part instead of an error;
  a message that expired before delivery can still be read by `messageId`.
- **5k.** `bridge_agents` asks the Codex app (`thread-owner-discovery`) for every Codex identity, retired ones too; a
  stuck app slows the whole listing.

## Assumptions (to be confirmed by the user)

1. **5a.** Without `since`, the de-duplication key uses the time the bridge first saw this waiting episode (kept in
   memory per session; cleared when the session is seen not waiting), so each new episode notifies once.
2. **5b.** The approval check looks only at agents with a Claude wake binding (`wake_targets`), the sessions the bridge
   already watches for wake. An unreadable registry directory gives `unknown` (no notice, `bridge_agents` says
   `unknown`), a readable one without the session still gives `stopped`.
3. **5e.** `bodyOffset` greater than the body length is an error naming the length. Reading an expired message by its
   `messageId` stays allowed on purpose (an explicit id is a history read, like `includeExpired`), and the part says
   `deliveryState: "expired"` so the reader knows it was never delivered.
4. **5k.** Retired identities get no presence lookup; `bridge_agents` shows them as retired without asking any host.
5. Bridge change: `UPSTREAM.md` and `UPSTREAM.sha256` in the same commit (D24); upgrading the runtime is needed.

## Decisions

- **D175 approval notice per episode.** Assumption 1.
- **D176 presence only where it is ours to read, unknown when unreadable.** Assumptions 2 and 4.
- **D177 offset errors, expired reads labelled.** Assumption 3.

## Requirements

1. Red first (bridge tests): two waiting episodes without `statusUpdatedAt` give two notices, one episode gives one.
2. Red first: an unbound Claude agent with an unhandled message is not checked; an unreadable registry directory gives
   `unknown` and no notice.
3. Red first: `bodyOffset` past the end throws; an expired message read by id carries `deliveryState: "expired"`.
4. Red first: `bridge_agents` with a retired Codex identity makes no IPC call for it.
5. `UPSTREAM.md`/`UPSTREAM.sha256` updated; `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Always: read only; nothing is answered or approved for the user.
- Never: poll every Claude session on the Mac.

## Acceptance (coordinator, after 0.6.1 — not done here)

- A2: first measure whether Claude Code itself already notifies when a background session waits for approval (not yet
  measured); Codex waiting for approval still shows as running in the directory (known gap, unchanged).
- An auto-mode Claude session is woken by a message.

## Open questions

None beyond the assumptions above.
