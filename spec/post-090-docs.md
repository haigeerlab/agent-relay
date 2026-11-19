# Spec: post-090-docs

<!-- spec-guard: review approved 38ce482a952e -->

## Objective

The hooks, tests and docs half of ledger item AJM8B1H ("follow-up fixes after the freeze"): review suggestions left
open by request-closing and claude-plugin-label, and an upgrade step found while upgrading to 0.9.2. Requested by the
user in the owner session ("可以", then "开始"); assumptions confirmed by the user in this session on 2026-10-24.
Released together with `post-090-bridge` as **0.9.3**. Nothing here changes bridge runtime files.

Readers: the user; the owner session (review, release, acceptance).

## What exists today (main 538c6c3, v0.9.2)

- `spec/request-closing.md` revision assumption 4 says D35 and the idempotency comparison are unchanged; both now use
  `closableBy` (exact match first, then lenient).
- `bridge/test/request-closing.test.ts:122` "two bridge processes cannot both close one request" runs sequentially and
  exercises the pre-check (the catch path is covered by the lost-race test near line 401); the lost-race test does not
  check that no read was recorded.
- `hooks/native_collaboration_doctor.py` `_plugin_labels` (claude-plugin-label D246–D247):
  - records whose project folder is gone are only counted: the note says "N records whose folder is gone carry an old
    label", with no advice;
  - the cleanup command is built as `cd %s && …` with the raw path;
  - every live non-user record gets `cd <project> && claude plugin uninstall|update --scope <scope> …`, also a
    `project` scope record, whose uninstall or update rewrites that repository's committed `.claude/settings.json`
    (no such record on this Mac; not measured);
  - steps are appended in listing order, so the user's `marketplace update` and `update` can sit between local
    uninstall commands.
- README zh/en "更新插件" and RELEASING "发版后" say a clone install needs only `git pull` and a new session. Measured on
  the 0.9.2 upgrade (2026-10-23): the user-scope record's label stays at the old version, so doctor's `claude-plugin`
  warns until `claude plugin marketplace update agent-relay-marketplace` and
  `claude plugin update --scope user agent-relay@agent-relay-marketplace` are run.
- Measured on the 0.9.1 acceptance: a local record whose folder is gone is removed by recreating the folder (with
  `git init` when it was inside a git repository), running `claude plugin uninstall --scope local
  agent-relay@agent-relay-marketplace` in it, then deleting the folder.

## Assumptions (confirmed by the user, 2026-10-24)

1. **request-closing wording and tests.** Revision assumption 4 is reworded to say D35 and the idempotency comparison use
   `closableBy` (exact first, then lenient); test 122 is renamed to say it checks the pre-check skip in sequence; the
   lost-race test also asserts that no read was recorded for the skipped id. (D238's change and the catch's error are in
   `post-090-bridge`.)
2. **Folder-gone records.** Still not warned about and not listed one by one; the note adds that they can stay or be
   removed by the user, and the measured way to remove one (assumption above). D247's text in
   `spec/claude-plugin-label.md` gets a dated revision note.
3. **Quoted paths.** The `cd` path in every cleanup command is `shlex.quote`d.
4. **Project scope: no command, a note.** A `project` scope record whose label disagrees is still reported (same label
   line, still `warn`), but gets no cleanup command; the note says the record is kept in that project's committed
   `.claude/settings.json`, so changing it changes the repository, and it is the user's call. Folder-gone and `local`
   records are unchanged apart from assumptions 2 and 3. The older-copy branch (`claude plugin update --scope project`
   when the loaded copy is older) is not in scope.
5. **Grouped steps.** `next` lists the user-scope steps first (`marketplace update`, then `update --scope user`), then
   the per-project commands sorted by folder; no step is repeated.
6. **README.** zh and en "更新插件": records whose folder is gone are not warned about and not listed; a project-scope
   record gets a note, not a command.
7. **Clone upgrade steps.** README zh/en "更新插件" (clone install), RELEASING "发版后" step 1 and RELEASING's rule for the
   CHANGELOG "从上一版升级" section add the two label-refresh commands after `git pull`, saying they only refresh the label
   shown by `claude plugin list` and silence doctor's warn. The 0.9.3 CHANGELOG upgrade section uses them.
8. **Out of scope.** Bridge runtime files, the host and the records on this Mac.

## Decisions

- **D256 request-closing follow-ups.** Assumption 1; `tasks/request-closing/todo.md`'s three "Open:" lines are ticked
  with a pointer here (the D238 one points to D253).
- **D257 doctor cleanup advice refined (revises D247).** Assumptions 2–6; `tasks/claude-plugin-label/todo.md`'s module
  review checkpoint is ticked (review done, nothing required).
- **D258 clone installs refresh the label.** Assumption 7.

### Folder-gone project scope records (2026-11-20, ledger M04WZ94 item 2, after 0.9.5)

The module review of #161 found that `_plugin_labels` counts every folder-gone record, whatever its scope, and the
note always gives `--scope local`; assumptions 2 and 4 did not cover a `project` scope record whose folder is gone.
Measured on Claude Code 2.1.328 with a throwaway `HOME`/`CLAUDE_CONFIG_DIR` and a local directory marketplace (no real
record touched):

- Deleting the project folder removes its `.claude/settings.json`, but the record stays in
  `~/.claude/plugins/installed_plugins.json` and in `claude plugin list --json`. A record's `enabled` follows the
  settings in effect where the listing runs, so with a user-scope install the folder-gone project record is listed as
  `enabled: true` and reaches `_plugin_labels`.
- `claude plugin uninstall --scope local …` in the recreated folder fails ("installed in project scope, not local");
  `--scope project` run anywhere else fails ("not installed in project scope").
- `claude plugin uninstall --scope project …` run in the recreated empty folder removes the record and creates no file
  (no `.claude/` in the folder or its parent repository). It worked with and without `git init`, also inside another git
  repository; so did `--scope local` for a local record.

- **D269 a folder-gone record is removed with its own scope.** Still counted, not warned about and not listed
  (assumption 2); the note names the scope's command: `--scope local` or `--scope project`, both (with "the one
  matching the record's scope") when both are present. Assumption 4's no-command rule does not apply: the folder is
  recreated empty, so nothing committed is changed. The `git init` clause stays (harmless, measured on 0.9.1). Live
  records, the older-copy branch and README are unchanged (README already says "as it describes").

## Requirements

1. Red first (`test_doctor.py`, fixture listings): a folder-gone record's note carries the keep-or-remove advice; a
   project path with a space is quoted in the command; a live `project` scope mismatch is warned with the
   settings note and no command; a listing with local, user and local records lists the user steps first.
2. Red first (skill/README guards in `test_packaging.py` or the existing doc guards): README zh/en carry the folder-gone
   and project-scope sentences and the two clone-install commands; RELEASING "发版后" names them.
3. Test rename and the no-read assertion in `request-closing.test.ts`; `UPSTREAM.md` row and
   `python3 scripts/bridge-manifest.py` (test-only, runtime mark unchanged).
4. `spec/request-closing.md` assumption 4 wording; `spec/claude-plugin-label.md` revision note; CHANGELOG
   `[Unreleased]`.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Ask first: anything on this Mac's hosts or plugin records (none planned).
- Never: doctor running a cleanup command itself; advising a command that edits a committed file.

## Acceptance (owner session, after release)

- On this Mac, the clone-install steps of the 0.9.3 CHANGELOG leave doctor's `claude-plugin` `ok`.

## Open questions

None.
