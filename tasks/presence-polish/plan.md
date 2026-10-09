# Plan: presence-polish

Based on [`spec/presence-polish.md`](../../spec/presence-polish.md) (accepted by the user on 2026-10-09: assumptions
1–5, D175–D177). Branch `claude/presence-polish` from main after the `delegation-continue-parity` closeout. Second
module of 0.6.1; bridge only, so `UPSTREAM.md` and `UPSTREAM.sha256` change in every commit that touches
`bridge/` (D24) and the runtime must be upgraded. The round-2 coordinator is told the PR number.

Read while planning: the approval check is `WakeDispatcher` (`wake-dispatcher.ts:108-125`) over
`BridgeStore.claudeWaiting` (`bridge-store.ts:749`); presence is `claudePresence`/`codexPresence` (`presence.ts`);
`bridge_agents` reads presence for every summary (`server.ts:520-528`); `claudeSessions` (`claude-wake.ts:39-42`)
returns `[]` when the registry directory cannot be read, and its other callers (wake, liveness) rely on that;
`bridge_inbox {messageId, bodyOffset}` clamps the offset in `bodyPart` (`paging.ts:58-60`).

## Task List

### Task 1: approval notice once per waiting episode (D175)
Red first (`approval-notice.test.ts`): a session waiting twice without `statusUpdatedAt` (waiting → running →
waiting) gives two notices; staying in one episode across checks gives one. Green: when `since` is missing, the
dispatcher keys the episode by the time it first saw that session waiting (in memory, per session), cleared when the
session is seen not waiting.

### Task 2: presence only for bound sessions, unknown when unreadable (D176)
Red first (`approval-notice.test.ts`, `presence.test.ts`): an unbound Claude agent with an unhandled message is not
checked; an unreadable registry directory gives `unknown` (no notice) while a readable one without the session still
gives `stopped`; `bridge_agents` shows `unknown` for it. Green: `claudeWaiting` joins only Claude wake bindings; a
registry read that says "unreadable" (new `claudeSessionsOrNull`, leaving `claudeSessions` and its callers unchanged)
feeds `claudePresence` with `null`.

### Task 3: retired identities are not looked up (D176)
Red first (`presence.test.ts` / MCP integration): `bridge_agents {includeRetired: true}` with a retired Codex identity
makes no `thread-owner-discovery` call for it and shows it as retired. Green: retired summaries skip `presenceOf`.

### Task 4: offset errors, expired reads labelled (D177)
Red first (`long-messages.test.ts`): `bodyOffset` past the body length throws an error naming the length (offset equal
to the length of an empty body still reads); an expired message read by `messageId` carries
`deliveryState: "expired"`. Green: the check in the `bridge_inbox` handler (before `bodyPart`), the state in the part.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14 (includes `npm run check`); `UPSTREAM.md` rows and
`scripts/bridge-manifest.py` regenerated; CHANGELOG `[Unreleased]`.

### Task 5: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews the PR; the user merges; then `install-docs-accuracy`.
