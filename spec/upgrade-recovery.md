# Spec: upgrade-recovery

## Objective

`native_collaboration_runtime.py upgrade --confirm` runs on every release (it upgraded the real host for 0.2.1, 0.3.0
and 0.4.0). Its directory swap is not recoverable: if the process dies or a rename fails between moving the mailbox
into the new build and the final rename, `runtime/` can be missing or empty, with the mailbox in a hidden stage
directory, and nothing tells the user how to get back. `install` on an uninstalled runtime (reinstall around kept
history) has the same gap and also deletes its stage directory by a name derived from the UTC second, which another
call could own. There is no rollback command; the upgrade prints manual steps. Found by the 0.4.0 architecture review
(B7, B8, C10). The user decided (2026-10-08) to cover the runtime upgrade and reinstall only (the one-time state
migration tool is out of scope) and to add `rollback --confirm`. Last module of 0.5.0.

Readers: the user, who runs upgrades on the real host; the round-2 coordinator, who reviews the PR before the user
merges it and re-checks the upgrade when 0.5.0 is released.

## What exists today (main 64c6739, 2026-10-08)

- `hooks/native_collaboration_runtime.py:393-463` `upgrade_runtime`: checks ready, not current, no running server;
  picks a free `<UTC second>[-n]` stamp (acceptance-030-gaps D74); copies `mailbox/` to `backups/<stamp>/`; builds
  `.runtime-upgrade-<stamp>`; then moves `mailbox/` and `data/` into the stage and renames `runtime` →
  `runtime.previous-<stamp>` inside a guard that moves them back on an exception; the final `stage.rename(root)`
  (`:451`) is outside the guard; a failed verification swaps back and keeps the build as
  `.runtime-upgrade-failed-<stamp>`. A killed process at any point after the first move leaves no record.
- `:487-517` `_reinstall_around_history` (install on an `uninstalled` runtime): stage
  `.runtime-reinstall-<UTC second>` with no uniqueness check; `rmtree(stage)` on any failure (`:498`, `:513`); moves
  `mailbox/`, `data/` in, `root.rmdir()`, final `stage.rename(root)` (`:515`) outside the guard.
- `:319-323` `UPGRADE_ROLLBACK`: manual steps, returned in the upgrade result.
- `status` states: `absent`, `uninstalled`, `invalid`, `ready`; `main` exits 0 for `absent`, `ready`, `upgraded`,
  `current`, `uninstalled`. Commands: `status`, `install`, `probe`, `upgrade`, `doctor`, `uninstall`.
- `docs/collaboration-interface.md:65` lists the runtime commands (§2.3). Interface 1.4 is not released yet (0.5.0).

## Assumptions (accepted by the user 2026-10-08)

1. A swap journal `<state root>/runtime-swap.json` is written before the first move: kind (`upgrade`, `reinstall`,
   `rollback`), stamp, the directories involved, the mailbox row counts. It is removed after a verified success or a
   completed recovery.
2. An interrupted swap is always rolled **back**, never forward: `status` reports `interrupted` with the next step;
   `install`, `upgrade`, `rollback` and `uninstall` refuse while the journal exists and point to `recover --confirm`;
   `recover` puts mailbox and data back into the pre-swap runtime directory, restores its name, checks the row counts,
   and keeps the new build as `.runtime-<kind>-failed-<stamp>`.
3. The final rename is inside the guard: its failure rolls back like a failed verification.
4. Stage directories are unique (stamp plus a random suffix, created exclusively); a failure removes only the
   directory this call created.
5. `rollback --confirm` swaps back to the newest `runtime.previous-*`, carrying mailbox and data; same preconditions
   as upgrade (ready, no running server), mailbox backup first, journalled, row counts checked; the current build is
   kept as `runtime.rolled-back-<stamp>`; the result repeats the schema caveat (older plugin hooks read schema ≤ 4).
6. `rollback` and `recover` are listed in interface §2.3; as additions they belong to the unreleased 1.4, no 1.5.
7. Tests inject a failure or a stop at each step and show `recover` restores the pre-swap layout with equal row
   counts; reinstall never deletes another call's stage; validate on Python 3.9, 3.10, 3.14; a live check in a
   temporary HOME: upgrade from v0.4.0, `rollback`, upgrade again, then an interrupted upgrade recovered.
8. Docs: README upgrade/rollback paragraph, collaboration-ops skill, CHANGELOG; the PR is reviewed by the round-2
   coordinator before the user merges.

## Decisions

- **D104 journal.** `runtime-swap.json` (0600) beside `runtime/` with `{kind, stamp, runtime, stage, previous,
  counts, step}`; `step` is rewritten before each move (`moving-history`, `renaming-runtime`, `renaming-stage`,
  `verifying`) so recovery knows which directory holds the mailbox. Written with write-to-temp plus rename.
- **D105 recover.** `recover --confirm` (refuses without a journal, and while a bridge of either directory runs):
  wherever the journal says the mailbox and data are, they go back to the pre-swap runtime directory (for `upgrade`
  and `rollback`: `runtime` or the renamed old one; for `reinstall`: `runtime/`), the old directory gets its name
  back, the row counts are checked against the journal, the half-built directory is renamed
  `.runtime-<kind>-failed-<stamp>`, then the journal goes. Result `recovered` with the paths; `main` exits 0.
- **D106 guarded swap.** Upgrade and reinstall run the moves and the final rename inside one guard that, on any
  exception, performs the D105 steps inline (and removes the journal only when they succeed).
- **D107 stage names.** `.runtime-<kind>-<stamp>-<6 hex>`, created with `mkdir` (no `exist_ok`); only a directory
  this call created is ever removed.
- **D108 rollback.** As assumption 5; refuses when there is no `runtime.previous-*`, and names the one it will use in
  the result. The `upgrade` result's `rollback` text now names the command instead of manual steps.
- **D109 status.** `status` reports `{"state": "interrupted", "journal": {...}, "next": "recover --confirm ..."}`
  when the journal exists; doctor's runtime check shows it as fail with the same next step.
- **D110 docs and interface.** README upgrade paragraph (rollback, recover), collaboration-ops skill, §2.3 runtime
  row (`rollback`, `recover`, `interrupted`), CHANGELOG `[Unreleased]`.

## Requirements

0. Red first: each upgrade step (after the mailbox move, after `runtime` → previous, the final rename, verification)
   with a forced exception ends with the pre-swap layout and no journal; with a simulated kill (journal left, step
   set) `status` says `interrupted`, `upgrade` refuses, and `recover --confirm` restores the layout with equal row
   counts and a `.runtime-upgrade-failed-*` build.
1. Reinstall: the same for its steps; a pre-existing directory with the old stage name is never removed.
2. Rollback: swaps to the newest previous, carries mailbox and data, counts equal, keeps the current build, refuses
   without a previous, while a bridge runs, or while a journal exists; interrupted rollback recovered by `recover`.
3. Doctor shows `interrupted` as fail with the next step.
4. Validate on three Pythons; CI green.
5. Live check per assumption 7; temporary HOME to the Trash.

## Boundaries

- Always: the sealed state root in tests; mailbox backup before any swap; row counts checked after.
- Ask first: the real `~/.agent-relay`; deleting any `runtime.previous-*`, `rolled-back` or `failed` directory
  (never automatic); changing the state migration tool.
- Never: roll an interrupted swap forward; remove a directory this call did not create; merge before the round-2
  coordinator's review.

## Success criteria

No single failure or kill during upgrade, reinstall or rollback leaves the runtime without a way back: `status` says
so and `recover --confirm` restores the previous layout with the mailbox intact; `rollback --confirm` returns to the
previous runtime in one command.

## Open questions

None. Accepted by the user on 2026-10-08 ("继续" after the review request): assumptions 1–8, D104–D110.
