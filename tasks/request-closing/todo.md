# Todo: request-closing

- [x] Task 1: schema 7 and the closure rule (D216) — red first (`SCHEMA_VERSION` was 6, no table), then the v7 step and `OPEN_REQUEST` with no closure row; the two older tests that pinned schema 6 now migrate to the current schema (they drop `request_closures` when faking an old file)
- [x] Task 2: `alsoAnswers` (D217) — red first (six cases), then the list shape check up front, the open checks inside `deliver()`'s transaction after the idempotent returns, closure rows with a primary-key conflict turned into the readable refusal, `contentDifferences` comparing sorted lists, `replies`/`closedBy` in the outbox and status, `closed` in the `bridge_send` result (D222); two stores on one file cannot close one request twice
- [x] Task 3: the other requester (D218) — one `bridge` notice per requester and answer on the first request's thread (none to the answer's recipient, the answerer, a retired or unknown requester), `messagePart` reads the answer with `direction: "answer"`; red against a build without the notice call
- [x] Task 4: `withdraws` (D219) — red first (five cases), then the sender's own open requests to this recipient only, outcome `withdrawn` (a `replyTo` still wins, `closedBy` keeps withdrawn), no read and no notice, retries and a conflict with a later `alsoAnswers`; plus a forced failure after the closures rolls everything back, and an acknowledgement still closes nothing
- [x] Checkpoint (report): bridge green — `npm run typecheck` clean, `npm test` 249 pass
- [x] Task 5: hooks, skills and instructions (assumption 4, D221) — red first (doctor on a schema 7 file), then `MAILBOX_SCHEMA_VERSIONS` adds 7 and the rollback caveat names schema 7; the retire and delegation-backend tests that used 7 as "newer" now use the next version; `collab`, `session-routing`, the server instructions and `INSTRUCTIONS.md` say to list every answered request, withdraw what is not needed and trust `closed`; an MCP test sends both lists through the server
- [x] Task 6: interface 2.3 and bookkeeping — `interface.json` 2.3, `test_packaging`, `relay_status.py` docstring, `docs/collaboration-interface.md` (version line, `bridge_send`, `bridge_outbox`, `bridge_wake_status`, `bridge_inbox`), `UPSTREAM.md` row and manifest, `bridge/CHANGELOG.md` 0.8.0, CHANGELOG `[Unreleased]` with the upgrade order and both upgrade-window caveats; README status lines move to 2.3 in the release PR
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH (47 files, 854 tests each; bridge `npm run check` 250 ok)
- [x] Task 7: PR and CI — the four CI jobs green; the user merged #130 (9faf932) on 2026-10-17; #130 opened; round-2 review (#4551): D35 swallowed a resent reply's new `alsoAnswers`/`withdraws` (fixed: it folds only when the earlier reply closed the same lists, red first), and an overdue request is now expired before the closure checks (red first); item 3 ("closed shorter than the list") cannot happen any more, so the wording stays
- [x] Checkpoint (gate): module review — the round-2 coordinator reviewed spec/plan #129 (six additions, all in it) and #130 (one fix and one small item, both in 6bc3cf4, re-checked and passed); the user merged #129 (32c85f0) and #130 (9faf932)

## Revision 2026-10-19: already-closed requests are skipped (D237–D239; the user approved the spec the same day)

- [x] Task 8: skip instead of refuse in the store (D237, D238) — red first (10 cases failed), then green; the D35 retry fold looks for an exact match before a lenient one, so a resend with the same list still folds onto the reply that closed it
- [x] Task 9: `bridge_send` returns `skipped`; parameter descriptions, skills and instructions (D238) — red first (MCP test)
- [x] Task 10: interface 2.7 and bookkeeping (D239)
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10, 3.14 with Node v24.18.0 first on PATH (47 files, 883 tests each; bridge `npm run check` 279 ok)
- [x] Task 11: PR and CI — #146, the four CI jobs green; review asked of the round-2 coordinator (#8873, waiting while its session is not running); Auto-fix on
- [x] Checkpoint (gate): module review — the user merged #146 (4377d1f) on 2026-10-19 without waiting for the review, which became a post-merge review

## Post-merge review of the revision (round-2 coordinator, 2026-10-20)

No blocker: the lenient retry comparison neither closes the wrong request nor misses one; `closedState`'s order matches
the old checks (wrong ids still refuse first); the lost-race test is sound. Open (low, after the release freeze):

- Done 2026-10-24 (`post-090-bridge` D253, the user's decision; interface 2.9): When the lenient D35/idempotency match folds a retry, `skipped` is `[]` even for ids closed elsewhere, so the
  sender sees such an id in neither `closed` nor `skipped`; compute them from `closedState` (this changes D238's "a
  duplicate retry returns `skipped: []`", so it needs the user's decision).
- Done 2026-10-24 (`post-090-docs` D256): The spec revision's assumption 4 says D35 and the idempotency comparison are unchanged; both now use
  `closableBy` (exact match first, then lenient). Say so in the spec.
- Done 2026-10-24 (`post-090-docs` D256 for the rename and the no-read assertion, `post-090-bridge` D254 for the catch): Rename the test "two bridge processes cannot both close one request" (it runs sequentially and exercises the
  pre-check; the catch path is covered by the lost-race test), add a no-read assertion to the lost-race test, and make
  `closeRequests`' catch handle a missing closure row with a readable error.

