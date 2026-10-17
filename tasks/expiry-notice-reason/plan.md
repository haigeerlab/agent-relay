# Plan: expiry-notice-reason

Based on [`spec/expiry-notice-reason.md`](../../spec/expiry-notice-reason.md) (accepted by the user on 2026-10-17:
assumptions 1–6, D215, including the send-time warning in `addressing.ts`; assumption 7 added after the round-2 review
of #126 and accepted the same day). This branch carries the map row, spec and
plan as one PR; the implementation goes on `claude/expiry-notice-impl` from main after that PR is merged. Only module of
0.7.2; the release PR waits until the implementation PR is merged. The round-2 coordinator and the usage observer are
told every PR number.

## Task List

### Task 1: one predicate, and the Claude-offline text (notices)
Red first in `test/delivery.test.ts` (requirement 1): a Claude job expired with `pendingReason: "offline"` gets a notice
that says the session was not running and asks the user to open it, without `crossSessionInbound` or `Bypass`;
`unreachable` keeps the existing unreachable text; the existing Claude expiry receipt and a `held` job still get
`CLAUDE_HOLD_EXPLANATION`; a Codex job never does. Green in `notices.ts`: export one predicate (D215) — Claude target and
state `held`, or state `refused` with Claude's expiry receipt — and give `explainFailure` the Claude-offline branch. The
receipt detail becomes a named constant in `claude-wake.ts` so the predicate compares with it, not with a regex.

### Task 2: the same predicate in `bridge_wake_status` and the send-time warning
Red first in `test/mcp-integration.test.ts` (requirement 2: offline expiries only → no `explanation`; a re-armed job
only → none; one real hold → `explanation`) and `test/lifecycle.test.ts` (requirement 3: three Claude offline expiries → the "last 3 background
pings" warning without the hold text and with the not-running sentence; three expiry receipts → with the hold text).
Green: `server.ts` list mode and `addressing.ts` use the predicate; `addressing.ts` attaches the hold text only when the
latest of the three is a hold, and the shared not-running sentence when it is a Claude offline expiry.
`health()` already returns `state`, `detail` and `app`, so the predicate takes `{ app, state, detail }` and works on both a
`WakeJob` and a `health()` row; no query change.

### Checkpoint (report): bridge green
`npm run typecheck` clean, `npm test` all pass; no `/expired|held/` regex left on wake details (`grep`).

### Task 3: bookkeeping
`UPSTREAM.md` row and `python3 -B scripts/bridge-manifest.py` (D24); `bridge/CHANGELOG.md` and root CHANGELOG
`[Unreleased]` (bridge change, needs `upgrade --confirm`); `bridge/INSTRUCTIONS.md` line on "held or expired"
(assumption 7); `docs/BACKGROUND-WAKE.md` if it says when the hold explanation appears.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 4: PR and CI
Push `claude/expiry-notice-impl`, open the PR, tell the coordinator and the observer; the CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.7.2 release PR (versions, README status lines), which also waits
for the user.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| A real Claude hold has a detail the predicate no longer recognises | the hold text disappears where it was right | Task 1 keeps the existing receipt test and adds a `held` case; the receipt detail is a shared constant |
