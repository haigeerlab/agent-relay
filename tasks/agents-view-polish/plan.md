# Plan: agents-view-polish

Based on [`spec/agents-view-polish.md`](../../spec/agents-view-polish.md) (accepted by the user on 2026-10-17:
assumptions 1–7 with item 5 = (a), D223–D227, D226 widened to `bridge_send` at approval; assumption 7 from the round-2 review of #132, accepted the
same day). This branch carries the map
row, spec and plan as one PR; the implementation goes on `claude/agents-view-polish-impl` from main after that PR is
merged. Only module of 0.8.1; the release PR waits until the implementation PR is merged. The round-2 coordinator and
the usage observer are told every PR number.

## Task List

### Task 1: `bridge_agents` pages; retired entries compact (D223)
Red first in the new `test/agents-view.test.ts` through the MCP server: 30 retired identities with long notes and
capabilities, `includeRetired` with a small `maxChars` pages with `hasMore`/`nextAfterName` to the end, every identity
once, in registration order; retired entries carry only the compact fields; an unknown `afterName` is refused; a call with no
parameters is not paged even past the default budget (every active identity, every field, `count` the total,
`hasMore: false`). Green: `agentSummaries` gains an `afterName` cursor on
(registered_at, name); `server.ts` builds entries, compacts retired ones and fits the page with `textCost` (at least one
entry per page) only when `includeRetired`, `maxChars` or `afterName` is given.

### Task 2: message status open to every caller (D224)
Red first: a third session's `bridge_wake_status {messageId}` returns the status (MCP test); a nonexistent id still
says `No message #N.` Green: `statusFor` drops the party check; the description says anyone may ask.

### Task 3: Claude presence `activity` (D225)
Red first in `test/presence.test.ts`: `busy` → `running` + `activity: busy`;
`idle` → `activity: idle`; `waiting`, unknown or missing status → no `activity`; Codex → none. Green in `presence.ts`.

### Task 4: the 2 s cap (D226)
Red first: an MCP server with a temporary HOME whose `~/.codex/ipc/ipc.sock` accepts and never answers (the fake from
`codex-not-loaded.test.ts`), one registered Codex identity bound to a thread: `bridge_agents` returns within 3 s with
that identity `not-loaded`; `bridge_send` to it returns within 3 s with its not-loaded warning. Green: pass
`AWAITING_PRESENCE_TIMEOUT_MS` to `codexOwner` in `bridge_agents`, `presenceOf` and the notice-location lookup.

### Checkpoint (report): bridge green
`npm run typecheck`, `npm test`.

### Task 5: interface 2.4 and bookkeeping (D227)
`interface.json` 2.4, `test_packaging`, `relay_status.py` docstring; `docs/collaboration-interface.md` (version line,
`bridge_agents`, `bridge_wake_status`, presence `activity`, and `not-loaded` possibly meaning no answer within 2 s); `UPSTREAM.md` row and manifest (D24, regenerated after the
last bridge edit); `bridge/CHANGELOG.md` 0.8.1; CHANGELOG `[Unreleased]` (no schema change, either order; runtime needs
`upgrade --confirm`).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 6: PR and CI
Push `claude/agents-view-polish-impl`, open the PR, tell the coordinator and the observer; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.8.1 release PR, which also waits for the user. Tell the Spec Guard
owner that interface 2.4 ships.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A consumer relied on `count` being the total | it counts one page in a paged call | a plain call is never paged and keeps `count` the total (round-2 review of #132) |
| 2 s is too short for a busy ChatGPT app | a loaded task shows `not-loaded` for one listing | H2 measured millisecond answers; the next call corrects it; the coordinator's acceptance watches for it |
| The fake socket test is timing-sensitive on CI | flaky | the bound is 3 s against a 2 s cap; the fake never answers, so the result does not depend on scheduling |
