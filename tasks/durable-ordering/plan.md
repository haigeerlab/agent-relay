# Plan: durable-ordering

Based on [`spec/durable-ordering.md`](../../spec/durable-ordering.md) (accepted by the user on 2026-10-07: cap 100,
refuse over the cap, drop redundant pings). Branch `claude/durable-ordering` from main 83f7e88. Every bridge change
updates `UPSTREAM.md` and `UPSTREAM.sha256` (`scripts/bridge-manifest.py`) in the same commit; red → green each task.

## Task List

### Task 1: Atomic claim and crash injection (assumption 4, D32)
`claim()` wraps the job update and the message move in one transaction; crash-injection tests (two stores on one temp
file, injected throw) before COMMIT on send, inside the claim, and between adapter call and `finish`: nothing
submitted twice, message and job states never contradict. **Files:** `src/wake-queue.ts`, new `test/durability.test.ts`.

### Task 2: Per-recipient order and redundant pings (assumptions 1, 2)
`claim()` SQL skips a job while an older job for the same agent is `pending`/`sending`; pending jobs whose message has
`read_at` are closed as `read` instead of pinged. Tests: X's second message waits behind its backing-off first; X
failing does not delay Y; two processes never have two pings to X in flight; already-fetched message not pinged.
Existing upstream tests adjusted only if their expectation is the old reordering (recorded).
**Files:** `src/wake-queue.ts`, new `test/ordering.test.ts`.

### Checkpoint (report): ordering and durability green

### Task 3: Pending cap (D30, D31)
`maxPendingPerRecipient()` (`BRIDGE_MAX_PENDING_PER_RECIPIENT`, 10 … 10 000, default 100); `insertMessage` counts the
recipient's unacknowledged, non-expired, non-failed direct messages inside the send transaction after the
idempotency return; at the cap → error; at ≥ 80 % → warning in the `bridge_send` result. Tests per spec req 4.
**Files:** `src/delivery.ts` (or `src/limits.ts`), `src/bridge-store.ts`, `src/server.ts`, new `test/pending-cap.test.ts`.

### Task 4: Docs
README (cap, setting, refusal), interface rows d and e done, checklist D15 wording, `UPSTREAM.md`.

### Task 5: Live D15 (temporary `AGENT_RELAY_HOME`, coordinator told first)
Two senders to one recipient while another recipient is offline: per-recipient order kept, the online recipient not
delayed, cap enforced with a low setting. No host config change.

### Checkpoint (gate): module review
