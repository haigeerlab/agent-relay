# Todo: idle-wake-batching

- [x] Task 1: schema 9 and explicit wake (D300, D307)
  - Codex implemented (`/delegate:run --write`); accepted by the owner: v9 migration (`wake_jobs.explicit_wake`), three-way `wake` from `bridge_send` / CLI `--wake`, conflicting flags refused. Owner fixes: `WakeJob.explicitWake` made optional (a required field broke fixtures in three tests outside the boundary); `request-closing.test.ts` schema pins 8 → 9 (added to the boundary, Spec change log). Bridge `npm run check` 353 pass; `validate.sh --quick` pass after removing an untracked `scripts/acceptance/__pycache__` that `test_ci_exempt_guard.py` could not read as text.
- [x] Task 2: hold and release in the queue and dispatcher (D299, D301–D304, D306)
  - Codex implemented; accepted by the owner after reading the whole diff: `idleHoldReason` (D299), `holdIdle` / `releaseHeld` / `heldAgents` / `heldAgentsNearExpiry` in `WakeQueue`, `CLAIMABLE` skips older holds and now waits for any `sending` job of the recipient (one in flight), `PENDING_EXPIRED` never expires a hold, `explicit_wake = 2` marks a released job (never held again, documented on the v9 migration), `checkHeld` shares one registry read per 30 s tick with `checkApprovals`, start-time release when `BRIDGE_IDLE_HOLD_MS=0`. A release restarts the job's `created_at` (wake window); `oldMessage` ignores that for released jobs. New `idle-hold.test.ts` 30 cases; existing wake tests unchanged. Bridge `npm run check` 383 pass; `validate.sh --quick` pass.
- [ ] Task 3: what the sender sees (D305)
- [ ] Task 4: interface 2.14, skills and docs (D308)
- [ ] Checkpoint (report): owner acceptance of Tasks 1–4
- [ ] Checkpoint (gate): push and open the PR
