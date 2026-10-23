# Spec: claude-plugin-label

<!-- spec-guard: review approved 9defbe14cefc -->

## Objective

Small follow-up module (doctor and docs only). Proposed on 2026-10-20 by the access monitor after a rehearsal; relayed by
the owner session. Timing of build and release is the user's call.

Claude Code keeps one record per install scope in `~/.claude/plugins/installed_plugins.json`, and `claude plugin list
--json` shows each record's `version`. On this Mac agent-relay has 13 enabled records (1 user, 12 local); the local ones
are labelled 0.6.1, 0.5.2 and 0.1.0, yet every one has `readFromFolder` = the main clone's `plugins/agent-relay`, so a
new session loads the clone's version (0.9.0 today). In the 2026-10-20 rehearsal two sessions read the label and
concluded 0.6.1 was loaded.

install-truth D184 made doctor's `claude-plugin` check compare only the copy a new session loads and ignore the label.
That check is `ok` on this Mac today; the stale cache copies behind the labels appear only as a long note inside the
`ok` detail. This module makes a label that disagrees with the loaded copy visible and says how to clear it.

Readers: the user; the round-2 coordinator (review, acceptance); the access monitor (proposer).

## What exists today (main efaae59, v0.9.0)

- `native_collaboration_doctor.py` `_claude_plugin`: per enabled record, the loaded copy is `readFromFolder` if set,
  else `installPath`; it warns only when a loaded copy's `plugin.json` version differs from the plugin doctor runs from.
  `installPath` copies that are not loaded and differ are listed in the detail ("is not loaded while readFromFolder is
  set"), state stays `ok`.
- Measured read-only on this Mac (2026-10-20): the listing's `version` equals the version of the record's
  `installPath` directory (`.../agent-relay/<version>`); `installed_plugins.json` has no `readFromFolder` field, the
  listing derives it. 5 of the 12 local records point at folders that no longer exist; 7 are live.
- README "升级" says the listing's version is not trusted and doctor reads `plugin.json`.

## Assumptions (to confirm before anything else)

1. **Own small module, not an install-truth rework.** It adds behaviour and reverses part of D184 ("the label is
   ignored"), so per the rework rule it is a new module (`add-module`), inserted after `script-access`, depending on
   `install-truth`. Module id `claude-plugin-label`.
2. **What counts as a mismatch.** For each enabled agent-relay record: label = the listing's `version`; loaded =
   version read from the loaded copy's `plugin.json` (rule unchanged). Mismatch = both readable and different. A record
   with no label is not a mismatch.
3. **State: `warn`.** Any mismatch on a record whose project folder exists (or a user-scope record) makes the check
   `warn`, which makes doctor's overall state `warn`. The detail names the label, the loaded version and the loaded
   path once per distinct label, so the reader learns "label 0.6.1, actually loads 0.9.0 from <clone>". Records whose
   folder is gone are only counted in the detail and never raise `warn` on their own (no Claude session can start
   there). Consequence: on this Mac doctor turns `warn` until the 7 live records are cleared — that is the point, but it
   is a visible change from today's `ok`.
4. **Cleanup advice, doctor never acts.** `next` lists, per live local record, `cd <folder> && claude plugin
   uninstall --scope local agent-relay@agent-relay-marketplace`, offered only when an enabled user-scope record exists
   (so the folder still gets the plugin); otherwise it offers `claude plugin update --scope local
   agent-relay@agent-relay-marketplace` in that folder. A user-scope mismatch gets `claude plugin marketplace update
   agent-relay-marketplace` then `claude plugin update --scope user agent-relay@agent-relay-marketplace`. Gone folders:
   the detail says they can be left or removed by the user. Each step is the user's to run, one by one; doctor writes
   nothing.
5. **Measured before the advice is coded, with the user's consent, after the 0.9.0 freeze ends** (it changes the
   Claude plugin install): (a) after the local uninstall, does a new session in that folder still load the clone via the
   user record; (b) does `claude plugin update --scope local` / `--scope user` refresh the label when the marketplace is
   a local clone; (c) can a record whose folder is gone be removed with the CLI at all. The advice in assumption 4 is
   corrected to whatever is measured; nothing is measured during the freeze.
6. **Merge, don't add.** The existing "not loaded while readFromFolder is set" note is replaced by the new wording; no
   second list of the same paths.
7. **Docs.** README "升级" gets one sentence: a `claude plugin list` version that disagrees with doctor is a stale
   label, doctor says how to clear it. The collab / collaboration skills tell agents to answer "which version is loaded"
   from doctor's `claude-plugin`, never from the listing's `version`.
8. **Release.** Patch release (0.9.1), interface unchanged; CHANGELOG `[Unreleased]` first. Building happens only in a
   worktree; no release, main-clone fast-forward or `codex plugin add` until the user ends the 0.9.0 freeze.

## Decisions

- **D246 a stale label is reported.** Assumptions 2, 3, 6.
- **D247 cleanup is advised, never done.** Assumptions 4, 5.

## Requirements

1. Red first (`test_doctor.py`, fixture listings): label = loaded → `ok`; the measured shape (live local records
   labelled 0.6.1 / 0.5.2 / 0.1.0, `readFromFolder` = a 0.9.0 copy, a user record labelled 0.9.0) → `warn` naming each
   label and the loaded version, with the uninstall advice; same without a user record → update advice instead; only
   gone-folder records mismatched → `ok` with a count; a missing or non-string label → no mismatch; the existing D184
   cases keep passing.
2. Red first (skill guards): README sentence and the skills' "ask doctor, not the listing" line are present.
3. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Ask first: every measurement in assumption 5; any `claude plugin uninstall` / `update` on this Mac.
- Never: doctor writes to Claude's plugin records or cache; editing `installed_plugins.json` by hand; anything that
  touches the frozen main clone.

## Acceptance (coordinator, after release)

- On a host with stale local labels, doctor's `claude-plugin` is `warn`, names the label and the loaded version; after
  the user runs the advised steps it is `ok` and `claude plugin list` shows no disagreeing label for live folders.

## Open questions

None. The user accepted all assumptions on 2026-10-20: assumption 3 uses `warn`; assumption 7 adds both the README
sentence and the skills line.

## Change log

- 2026-10-23: Task 3 host measurements (user consented step by step) matched assumption 4, so the advice is unchanged:
  (c) gone-folder records can be removed with the CLI by recreating the folder (`git init` inside it when it sits
  inside another repository), running `claude plugin uninstall --scope local …` there and deleting it again; (b) `update
  --scope local` moved a 0.1.0 label to 0.9.0 and `update --scope user` reported up to date; (a) after the local
  uninstall a new session in that folder loaded the clone (0.9.0) via the user record. Count corrected: 5 of the 12
  local records were gone, 7 live (was "6").
