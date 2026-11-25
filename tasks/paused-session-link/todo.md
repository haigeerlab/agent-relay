# Todo: paused-session-link

- [x] Task 1: schema 8 and the `desktop` field on `bridge_register` (D287, D288)
  - Accepted by the owner: new `desktop-link.test.ts` and schema tests; title cleanup also strips C1 controls; `request-closing.test.ts` pins schema 8; bridge `npm run check` 338 pass; `bash scripts/validate.sh` pass (51 files, 1082 tests).
- [x] Task 2: hooks read schema 8 (D288)
  - Accepted by the owner: `MAILBOX_SCHEMA_VERSIONS` gains 8, `ROLLBACK_CAVEAT` names schema 8 and read-only CLI commands; retire and doctor tests updated.
- [x] Task 3: one "not running" wording and the manual-wake sentence (D289, D291)
  - Accepted by the owner: new `paused-wording.test.ts`; owner fixes: first parts no longer repeat the cause, the notification body speaks to the user (no "Tell the user"), titles in single quotes; Spec D289 updated to match (to show at the final gate). Bridge `npm run check` 340 pass; `bash scripts/validate.sh` pass (51 files, 1086 tests).
- [x] Task 4: the offline notification opens the session (D290)
  - Accepted by the owner: offline notice gets `-open <link>` only with a revalidated stored link and terminal-notifier; title in the subtitle; osascript and other kinds unchanged (notify, notify-channel tests).
- [x] Task 5: `bridge_agents` carries `desktop` (D292)
  - Accepted by the owner: `desktop` only when stored; tool description updated; agents-view tests. `bash scripts/validate.sh` pass (51 files, 1089 tests).
- [x] Task 6: interface 2.12, skill, docs and bookkeeping (D293)
  - Accepted by the owner: new `test_paused_session_docs.py`; interface 2.12; skill and server instructions (D293); interface, notification and host-differences docs; CHANGELOG; `UPSTREAM.md` row. Owner fix: the interface doc names no release version (set at release, D252). `bash scripts/validate.sh` pass (52 files, 1095 tests).
- [x] Checkpoint (report): owner acceptance of Tasks 1–6
  - Codex review of the branch (`/delegate:review --backend codex`, gpt-5.6-sol high, base b5a6eb6): 6 blocking — static
    offline explanation in the 3-failures warning, title cut by UTF-16 units, schema-7 migration test not starting from
    schema 7, missing takeover/rebind and refusal tests, missing no-link D291 tests, broken `UPSTREAM.md` table. Fixed
    (7ad6740). Re-check of the fix commit (the whole-branch re-check exceeded Codex's 1 MiB input): 4 resolved, 2 left —
    D291 de-duplication by text scan (now an explicit flag) and no executable script-identity test (added to
    `script-cli.test.ts`). Both fixed by the owner.
  - `bash scripts/validate.sh` pass (52 files, 1100 tests); the branch diff has only made-up `local_` ids and no other
    project's name.
- [x] Checkpoint (gate): PR review and merge by the user
  - Merged by the user: PR #207 (merge commit aa8422c, 2026-11-26).
