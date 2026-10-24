# Plan: post-090-docs

<!-- spec-guard: review pending -->

Based on [`spec/post-090-docs.md`](../../spec/post-090-docs.md) (approved by the user on 2026-10-24: assumptions 1–8,
D256–D258). Built after `post-090-bridge` on the same branch `claude/unruffled-stonebraker-c923dd`; one PR for both
modules. Nothing here touches the main clone, the hosts or the plugin records on this Mac.

Found while planning (read-only, 2026-10-24, main 538c6c3):
- `test_doctor.py` already has the label cases at lines 648–790 (measured shape, no user record, lagging user record,
  folder-gone only, missing label); the new cases sit beside them and reuse their listing fixtures.
- `_plugin_labels` builds steps per record in listing order; the user steps are a fixed pair, so grouping is "user pair
  first, then project commands sorted by folder".
- The lost-race test is at `bridge/test/request-closing.test.ts:401`; test 122 is the sequential pre-check case.

## Task List

### Task 1: request-closing follow-ups (D256; assumption 1; requirement 3)
Rename test 122 to say it checks the pre-check skip when two closes run one after the other; add to the lost-race test
an assertion that no read was recorded for the skipped id. `spec/request-closing.md` revision assumption 4 reworded
(D35 and the idempotency comparison use `closableBy`, exact first, then lenient). Tick the three "Open:" lines in
`tasks/request-closing/todo.md` with a pointer to D256 (and D253 for the `skipped` one). `UPSTREAM.md` row,
`python3 scripts/bridge-manifest.py` (test-only; the runtime mark is unchanged — checked).

### Task 2: doctor cleanup advice (D257; assumptions 2–5; requirement 1)
Red first in `test_doctor.py`: (a) folder-gone records: the note says they can stay or be removed, and how (recreate the
folder, `git init` first if it was in a git repository, run `claude plugin uninstall --scope local
agent-relay@agent-relay-marketplace` there, delete the folder); state unchanged; (b) a live local record whose folder
has a space is shown as a `shlex.quote`d path in the command; (c) a live `project` scope mismatch: label line shown,
`warn`, the settings note, no command for it; (d) local, user, local in listing order: `next` gives the user pair first,
then the two local commands sorted by folder, no step repeated. Green: `_plugin_labels` and the note text in
`_claude_plugin`. `spec/claude-plugin-label.md` gets a dated revision line under D247 pointing to D257.

### Task 3: README, RELEASING, CHANGELOG (D257 assumption 6, D258; requirement 2, 4)
Red first: doc guards (in `test_packaging.py` beside the existing README checks) that README zh/en "更新插件" carry the
folder-gone sentence, the project-scope sentence and, under the clone install, the two label-refresh commands; and that
RELEASING "发版后" and its "从上一版升级" rule name them. Green: README.md and README.en.md (same section, same content),
RELEASING.md, CHANGELOG `[Unreleased]` (both modules, interface 2.9, runtime upgrade needed). Tick
`tasks/claude-plugin-label/todo.md`'s module-review checkpoint (review done, nothing required).

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 (Node 24 first on PATH); counts recorded in the todo.

### Task 4: PR and CI
Push, open one PR for both modules (Chinese title and body; links AJM8B1H; says interface 2.9, runtime upgrade needed,
the bridge version moves in the release PR); four CI jobs green; tell the owner session the PR number; ledger comment
on AJM8B1H.

### Checkpoint (gate): module review
The owner session's review of both modules; the user merges. Release 0.9.3 and the upgrade on this Mac are separate
steps the owner session asks of the user.

## Risks

- The folder-gone advice was measured only for local records; the note says "a local record", and project-scope
  folder-gone records get the same count but no method.
- Doc guards that pin exact sentences break on later rewording; they check the two commands and one key phrase each,
  as the existing README guards do.
