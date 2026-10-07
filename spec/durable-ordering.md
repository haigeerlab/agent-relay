# Spec: durable-ordering

## Objective

Prove that nothing is submitted before it is durable, keep each recipient's pings in message order without letting one
recipient hold up another, and bound how much undelivered work can pile up for one recipient. Interface gaps d and e;
checklist D15.

Readers: the user; the round 1 coordinator (D15); agents building `idempotency` and `identity-check`.

## What exists today (measured in the vendored bridge after delivery-state-machine, 2026-10-07)

- **Persist before submit holds for the send:** message row and wake job are one `BEGIN IMMEDIATE` commit before any
  host call (`bridge-store.ts:379-415`, `wake-queue.ts:82-90`). The ping is sent only after `claim()` has set the job
  `sending` with a 30 s lease (`wake-queue.ts:181-191`, `wake-dispatcher.ts:58-66`).
- **One seam is not atomic:** `claim()` sets the job `sending` and then moves the message to `sending` in a second
  statement (`wake-queue.ts:181-192`). A crash between them leaves job `sending`, message `queued`; the lapse sweep then
  makes the job `unknown` but `queued → unknown` is not an allowed move, so the message stays `queued` and could later
  `expire` although its ping may have gone out.
- Crash tests: only `wake-queue.test.ts:39` (reopen, lapse → `unknown`); none inject a failure between INSERT and
  COMMIT, between the two claim statements, or between the adapter call and `finish`.
- **Ordering:** `claim()` takes the oldest *due* pending job across all recipients (`ORDER BY id`, `retry_at <= now`).
  A later message to X is pinged while an earlier one to X is backing off, and across processes several pings to X can
  be in flight. The recipient still reads its whole inbox oldest-first (`inbox` `ORDER BY m.id`), and every wake says
  "read the inbox", so wake order changes timing, not processing order — but pings left `pending` after the recipient
  has already fetched everything become redundant wake turns.
- **Independence:** no SQL head-of-line blocking (a failing job steps aside via `retry_at`); each process dispatches
  one job at a time, so a slow adapter call delays that process's other recipients (Claude waits ≤ 1.8 s for a receipt).
- **Caps:** none on messages per recipient, inbox size, pending jobs or send rate; body has only `min(1)`.

## Assumptions

Confirmed by the user on 2026-10-07, including dropping redundant pings (assumption 2).

1. **Per-recipient order = dispatch order, not processing order:** at most one ping in flight per recipient, claimed
   and sent oldest first. What the recipient reads is unchanged — its inbox stays oldest-first by id, whatever order
   the pings arrive in. **Rule:** A pending job for X is not claimed
   while an older job for X is `pending` or `sending`. `unknown`, `held` and final states do not block (a lapsed or held
   head must not stall the queue). Other recipients are unaffected (the rule is per recipient, in the one `claim()`
   SQL, so it holds across processes).
2. **Redundant pings are dropped:** a pending job whose message the recipient already fetched (`read_at` set) is
   closed as `read` at claim time instead of waking the session again.
3. **The pending cap counts only undelivered direct messages: delivery state `queued`, `sending` or `unknown`**
   (user, 2026-10-07, refining the first wording after the round 1 coordinator's review). `accepted` (fetched or
   confirmed, even if not yet acknowledged), `failed`, `expired` and broadcasts do not count. Capacity is released when
   a message expires, is fetched or acknowledged (`unknown` → `accepted` by evidence), or fails. `unknown` never
   expires, so a recipient that never reads its mailbox stays at the cap — which is what the cap is meant to expose. It is checked inside the send transaction (atomic across processes), after the
   idempotency early return (a retry of a stored message still succeeds).
4. **The claim is one transaction:** the job update and the message move commit together, closing the seam above.
5. No schema change; no change to `relay_status` or `interface.json`.
6. **A message fetched but never acknowledged stays visible, not silent:** after assumption 2 it is never pinged again;
   `bridge_outbox` shows it as `deliveryState: accepted`, `wake: read`, `acknowledgedAt: null`, and `bridge_wake_status`
   shows its job `read` (tested).

## Decisions

D30 (default 100), D31 (refuse over the cap, warn at 80 %) and D32 accepted on 2026-10-07.

- **D30 cap default 100** pending messages per recipient, configurable with `BRIDGE_MAX_PENDING_PER_RECIPIENT`
  (10 … 10 000). A hundred unhandled requests to one session is already a sign something is wrong; the inbox pages at
  25–200. Alternatives: 50, 200.
- **D31 over the cap the send is refused** with an error naming the recipient, the count and the setting; at 80 % the
  send succeeds with a warning. Alternative: warn only, never refuse.
- **D32 crash-injection tests** at each seam — before COMMIT, inside the claim, between adapter call and `finish` —
  using two stores on one file and an injected failure, asserting nothing is submitted twice and no message is left
  in a state that contradicts its job.

## Requirements

1. Claim is atomic (assumption 4); a crash between its two writes is impossible by construction and tested.
2. Per-recipient order and independence (assumption 1) with tests: two messages to X, the first backing off → the second
   is not claimed; X failing does not delay Y; two processes never have two pings to X in flight.
3. Redundant pings dropped (assumption 2), tested.
4. Pending cap (D30, D31), tested: refusal at the cap, warning at 80 %, idempotent retry still accepted; expiry, fetch,
   ack (including `unknown` → `accepted`) and failure release capacity; accepted-unacknowledged and broadcasts not
   counted. Read-but-unacknowledged visibility (assumption 6) tested.
5. Crash-injection tests (D32).
6. `UPSTREAM.md` / `UPSTREAM.sha256`, README (cap and setting), interface rows d and e and checklist D15 updated.

## Testing strategy

TS unit tests in the bridge (two `BridgeStore` handles on one temp file for cross-process cases); `validate.sh` runs
them. Live (temporary `AGENT_RELAY_HOME`, no host config change): D15 — two senders to one recipient while another
recipient is offline; per-recipient order, no cross-recipient delay, cap enforced.

## Boundaries

- Always: keep persist-before-submit; never replay `unknown`; additive only.
- Ask first: a schema change; changing the cap's refusal into silent dropping.
- Never: drop or delete stored messages to enforce the cap; push without approval.

## Success criteria

1. All tests green, including crash-injection and cross-process ordering tests.
2. Live D15 passes against the target column.
3. Docs updated.

## Open questions

None.
