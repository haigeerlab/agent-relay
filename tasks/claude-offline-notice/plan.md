# Plan: claude-offline-notice

Based on [`spec/claude-offline-notice.md`](../../spec/claude-offline-notice.md) (accepted by the user on 2026-10-15:
assumptions 1–8, D193). Branch `claude/claude-offline-impl` from main after this plan's PR. Only module of 0.6.7; the
round-2 coordinator is told every PR number; the release PR waits until the implementation PR is merged.

## Task List

### Task 1: the offline notice for Claude recipients
Red first in `test/notify.test.ts`: the cases of requirement 1. Green: in `wake-dispatcher.ts`, a Claude branch next to
the Codex one; a store query for the recipient's pending offline jobs (count, earliest message and time); one
`notifyUndelivered` call keyed `claude-offline-<agent>-<earliest message id>` so a spell notifies once and a new spell
gets a new key; notice text in `notify.ts` (a new `kind: "offline"`), no body, no `where`.

### Task 2: the sender sees the reason
Red first (outbox test): `wake.pendingReason` for pending jobs; the plain detail for a pending Claude job. Green:
`bridge-store.ts` outbox query and `claude-wake.ts` detail texts.

### Task 3: bookkeeping
`UPSTREAM.md` row, manifest, CHANGELOG `[Unreleased]` (needs `upgrade --confirm`), `docs/BACKGROUND-WAKE.md`.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`.

### Task 4: real check — **ask the user first**
With the worktree's bridge against a scratch mailbox: a recipient bound to a Claude session id with no live process;
send, wait five minutes; read the notice (log first, then one real banner if the user agrees); read the outbox.

### Task 5: PR and CI
Push, open the PR, tell the coordinator; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews; the user merges; then the 0.6.7 release PR.
