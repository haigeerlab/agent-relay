# Plan: takeover-wake-rebind

Based on [`spec/takeover-wake-rebind.md`](../../spec/takeover-wake-rebind.md) (assumptions 1–6 and D186 accepted by
the user on 2026-10-10). Branch `claude/takeover-wake-rebind` from main 6497f41. Red → green, one commit per task.

## Task List

### Task 1: takeover replaces a wake binding (D186)
Bridge tests in `test/identity.test.ts` first (red: B's `takeover: true, wake: "auto"` fails with "already bound to
another session"): A binds `wake: "auto"` and has a pending wake job; B with `takeover: true, wake: "auto"` → ok,
`wake` is B's session, note "taken over", A's job `cancelled`, message still unread; the same with an explicit
`wake: {app: "claude", sessionId}`; B without `takeover` refused, binding unchanged; B with `takeover` and no `wake`
keeps A's binding; A again with `wake: "auto"` unchanged. Then `wake-queue.ts`: `bind(agent, target, {replace})`
does delete, cancel pending and insert in one `atomically` step; `server.ts` passes `replace` only when `takeover`
resolved a binding conflict. `UPSTREAM.md` row, `python3 -B scripts/bridge-manifest.py`, CHANGELOG `[Unreleased]`
(needs `upgrade --confirm`).
**Files:** `bridge/src/wake-queue.ts`, `bridge/src/server.ts`, `bridge/test/identity.test.ts`, `bridge/UPSTREAM.md`,
`bridge/UPSTREAM.sha256`, `CHANGELOG.md`.

### Checkpoint (report): `scripts/validate.sh` with Node 24 on PATH + bridge `npm run check`

### Task 2: PR and CI
Push, open the PR (Chinese), CI green.

### Checkpoint (gate): module review
