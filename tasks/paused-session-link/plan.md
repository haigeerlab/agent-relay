# Plan: paused-session-link

<!-- spec-guard: review approved -->

Based on [`spec/paused-session-link.md`](../../spec/paused-session-link.md) (approved by the user on 2026-11-26:
assumptions 1–8, D287–D293). Built on branch `claude/paused-session-link` from main b5a6eb6; one PR. ecosystem-lead has
no objection to interface 2.12 (mailbox #23082) and asked for three things this Plan carries: made-up UUIDs only in
tests and docs, a release notice naming interface 2.12 / the `desktop` field / schema 8 with `upgrade --confirm`, and
asking the user before the acceptance step that stops a test session. Codex implements each task; the owner accepts
(diff, focused tests, `bash scripts/validate.sh --quick`, full run before the PR). Nothing here touches the main clone,
the hosts, the runtime or the mailbox on this Mac.

Found while planning (read-only, main b5a6eb6):
- `bridge/src/schema.ts` `MIGRATIONS` adds columns with `addColumn` (v5 `host_app`/`host_session`, v6
  `expects_reply`); a writable older bridge opens a newer database (`newer: true`), but a read-only open
  (`bridge-store.ts:296`, used by the CLI's `agents` / `outbox` / `sessions`) throws `ReadOnlyMailboxError` when the
  version is not its own. Spec requirement 2 was corrected to say this (Codex plan review, 2026-11-26).
- `hooks/native_collaboration_runtime.py:25` `MAILBOX_SCHEMA_VERSIONS = (2, …, 7)` is what retire and doctor accept;
  `ROLLBACK_CAVEAT` (`:488`) names schema 7 and the hook versions per release.
- `bridge/src/server.ts` `bridge_register` (input schema ~L160, handler after it) already distinguishes a verified
  `caller.host` from a claimed Codex `host` (D75); `desktop` follows the verified path.
- Texts to change: `addressing.ts` (stopped warning ~L116), `claude-wake.ts` `CLAUDE_NOT_RUNNING` (L87),
  `notify.ts` `noticeText`/offline title (L91, L125), `notices.ts` `CLAUDE_OFFLINE_EXPLANATION` (L31).
- Offline notice: `wake-dispatcher.ts` `noticeClaudeOffline` builds `{kind: "offline", …}` with no `where`;
  `notify.ts` adds click arguments only from `notice.where` (`clickArgs`, `location.ts:101`).
- `hooks/test_packaging.py` pins `interface.json`; `hooks/relay_status.py` lists the interface history.

## Task List

### Task 1: schema 8 and the `desktop` field on `bridge_register` (D287, D288; requirements 1–2, bridge side)
Red first, new `bridge/test/desktop-link.test.ts` and `schema.test.ts`:
(a) a schema-7 database migrates to 8 with `agents.desktop_link` / `desktop_title` NULL and no other change;
(b) a Claude session (verified host) registering with `desktop: {link, title}` stores both; a second register without
`desktop` keeps them; `desktop: null` clears them; takeover by another session or a new wake binding clears them unless
that call passes its own;
(c) a link not matching D287's pattern is refused; a title with control characters / runs of spaces / 300 characters
is stored cleaned and cut to 120; an empty title stores none;
(d) a Codex task (claimed `host`), a script identity and a caller without a verified host are refused with D287's
sentence;
(e) the built CLI's read-only commands (`agents`, `outbox`) read a schema-8 mailbox, and a read-only store opened on a
schema-9 database still throws `ReadOnlyMailboxError` with the existing message (`script-cli.test.ts` or
`schema.test.ts`).
Green: `schema.ts` v8 migration, `SCHEMA_VERSION = 8`; store read/write of the two columns; `server.ts` input schema and
handler; one validator (`src/desktop-link.ts`). All UUIDs in tests are made up.

### Task 2: hooks read schema 8 (D288; requirement 2, hooks side)
Red first (`hooks/test_*`): retire and doctor accept a schema-8 mailbox; `newer_mailbox_schema(9)` still reports newer;
`ROLLBACK_CAVEAT` names schema 8. Green: `MAILBOX_SCHEMA_VERSIONS` gains 8; `ROLLBACK_CAVEAT` reworded for schema 8
(older plugins' hooks read up to 7 for 0.9.x).

### Task 3: one "not running" wording and the manual-wake sentence (D289, D291; requirement 3)
Red first (`addressing`, `notices`, `notify` tests): the send warning, `CLAUDE_NOT_RUNNING`, `noticeText` for
`offline` and `CLAUDE_OFFLINE_EXPLANATION` carry D289's sentence, naming the session by `"<title>" (mailbox name
<agent>)` when a title is stored and by `<agent>` otherwise; D291's sentence (with `local_<uuid>` taken from the stored
link) appears in the send warning and the expiry notice only when a link is stored, and never in `noticeText`. Green:
the four texts read the stored `desktop` through the store.

### Task 4: the offline notification opens the session (D290; requirement 4)
Red first, `notify.test.ts` with the notice log: an offline notice for a recipient with a stored link passes
`-open <link>` to terminal-notifier and shows the title in its subtitle; without a link, on the osascript channel, and
for every other notice kind, no `-open`; `notify.off` / `AGENT_RELAY_NOTIFY=off` silence it; no message body. Green:
`noticeClaudeOffline` passes the stored link and title; `notify.ts` adds `-open` only for kind `offline` with a link
that passes D287's validator again at use.

### Task 5: `bridge_agents` carries `desktop` (D292; requirement 5)
Red first, `agents-view.test.ts`: an entry with a stored link carries `desktop: {link, title}` (title omitted when
none); without a link, no `desktop`; retired short entries never carry it. Green: the agents view and the tool
description.

### Task 6: interface 2.12, skill, docs and bookkeeping (D293; requirements 6–7)
Red first: `test_packaging.py` expects `"interface": "2.12"`; a new `hooks/test_paused_session_docs.py` expects
(a) `skills/collab/SKILL.md` and the server instructions to name `get_session` with `"self"`, the `desktop` field and
"never another session's link"; (b) `docs/collaboration-interface.md` to name `desktop` under `bridge_register` and
`bridge_agents` and the version 2.12; (c) both notification docs to say the offline notice opens the session when a
link is recorded; (d) `docs/host-differences.md` H4 to record the measured link click; (e) CHANGELOG `[Unreleased]` to
name `desktop`, interface 2.12 and schema 8; and that none of these files contains a `local_` id other than the
placeholder `local_<uuid>` or the made-up test id. `test_bridge_vendoring.py` already fails when `UPSTREAM.sha256` is
not regenerated. Green: `interface.json`; `relay_status.py` history line;
`docs/collaboration-interface.md` §1 version line and the `bridge_register` / `bridge_agents` fields;
`skills/collab/SKILL.md` join step and the server instructions in `server.ts` (D293: call `get_session("self")` when
the tool exists, pass `desktop`, never another session's link); `docs/notifications.md` / `notifications.en.md`
(clickable offline notice); `docs/host-differences.md` H1/H4 with the measured facts in the Spec (no real session ids);
CHANGELOG `[Unreleased]`; `UPSTREAM.md` rows for changed bridge files and `python3 -B scripts/bridge-manifest.py`.

### Checkpoint (report): owner acceptance of Tasks 1–6
Full `bash scripts/validate.sh` green on this branch; `/delegate:review` of the branch diff against the Spec (findings
fixed or recorded here); a grep that no real `local_` id of this Mac is in the diff.

### Checkpoint (gate): PR review and merge by the user
Before it: commit list and changed-files table shown to the user; push and opening the PR are asked first (remote
write). Merging needs CI green (requirement 8): the merge follows CLAUDE.md F3 — `gh pr merge --merge` only when
`mergeStateStatus` is `CLEAN`, otherwise `gh pr merge --auto --merge`, which GitHub completes only after `CI required`
passes; a CI failure is fixed on the branch, never merged around. After the merge: reply to ecosystem-lead with the PR number. Release (version, tag, `upgrade --confirm`, the
release notice ecosystem-lead asked for) and the real-host acceptance in the Spec are separate steps, asked first.

## Files likely touched

- Bridge: `src/schema.ts`, `src/bridge-store.ts`, `src/server.ts`, new `src/desktop-link.ts`, `src/addressing.ts`,
  `src/claude-wake.ts`, `src/notices.ts`, `src/notify.ts`, `src/wake-dispatcher.ts`, the agents view source; tests
  `test/desktop-link.test.ts` (new), `schema.test.ts`, `notify.test.ts`, `agents-view.test.ts`, addressing / notices
  tests; `UPSTREAM.md`, `UPSTREAM.sha256` (via the manifest script).
- Hooks: `native_collaboration_runtime.py`, `relay_status.py`, tests for retire / doctor / packaging.
- Plugin: `interface.json`, `skills/collab/SKILL.md`.
- Docs: `docs/collaboration-interface.md`, `docs/notifications.md`, `docs/notifications.en.md`,
  `docs/host-differences.md`, `CHANGELOG.md`.
- No new dependency; no `.github/` change; no change to `scripts/ci_scope.py`.

## Risks and mitigations

- **A session passes another session's link.** Only a verified Claude host may pass `desktop`, the bridge records it
  as a claim (D287), and its only effect is which session a click opens; the skill says never another session's link.
- **Schema bump and rollback.** After a rollback to 0.9.6 its bridge still opens the schema-8 mailbox (compatible
  mode), but its read-only CLI commands and hooks refuse it; `ROLLBACK_CAVEAT` says so for schema 8 (roll the plugin
  back too, or restore the backup), and the release notes say `upgrade --confirm`.
- **Manual waking adds memory pressure.** D291 is words only, says "not unasked or repeatedly", and never reaches the
  user-facing notification; the bridge calls nothing.
- **Real ids leak into a public repo.** Made-up UUIDs only; the report checkpoint greps the diff.
- **Codex's sandbox cannot run every test** (sandbox-exec). The owner runs `validate.sh` locally for each task.

## Open questions

None.

## External review

- 2026-11-26, Codex (`/delegate:review --backend codex`, gpt-5.6-sol, high), plan as first written: 4 blocking.
  (1) requirement 2 contradicted the real rollback behaviour — the Spec was wrong, corrected (writable old bridge opens
  schema 8 in compatible mode; read-only CLI and hooks refuse); (2) no CLI schema-reader test — added to Task 1 (e);
  (3) Task 6 had a red test for the version only — `test_paused_session_docs.py` added; (4) no CI-green merge rule —
  stated in the final gate. Fixed plan goes to the user with the Spec revision (`--target both`).
