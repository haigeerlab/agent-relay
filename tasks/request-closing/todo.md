# Todo: request-closing

- [x] Task 1: schema 7 and the closure rule (D216) — red first (`SCHEMA_VERSION` was 6, no table), then the v7 step and `OPEN_REQUEST` with no closure row; the two older tests that pinned schema 6 now migrate to the current schema (they drop `request_closures` when faking an old file)
- [x] Task 2: `alsoAnswers` (D217) — red first (six cases), then the list shape check up front, the open checks inside `deliver()`'s transaction after the idempotent returns, closure rows with a primary-key conflict turned into the readable refusal, `contentDifferences` comparing sorted lists, `replies`/`closedBy` in the outbox and status, `closed` in the `bridge_send` result (D222); two stores on one file cannot close one request twice
- [x] Task 3: the other requester (D218) — one `bridge` notice per requester and answer on the first request's thread (none to the answer's recipient, the answerer, a retired or unknown requester), `messagePart` reads the answer with `direction: "answer"`; red against a build without the notice call
- [x] Task 4: `withdraws` (D219) — red first (five cases), then the sender's own open requests to this recipient only, outcome `withdrawn` (a `replyTo` still wins, `closedBy` keeps withdrawn), no read and no notice, retries and a conflict with a later `alsoAnswers`; plus a forced failure after the closures rolls everything back, and an acknowledgement still closes nothing
- [x] Checkpoint (report): bridge green — `npm run typecheck` clean, `npm test` 249 pass
- [ ] Task 5: hooks, skills and instructions (assumption 4, D221)
- [ ] Task 6: interface 2.3 and bookkeeping
- [ ] Checkpoint (report): local validation
- [ ] Task 7: PR and CI
- [ ] Checkpoint (gate): module review
