# Plan: runtime-mark-scope

<!-- spec-guard: review pending -->

Based on [`spec/runtime-mark-scope.md`](../../spec/runtime-mark-scope.md) (approved by the user on 2026-10-23:
assumptions 1–9, D248–D250). Built on branch `claude/gallant-nobel-b7b8fe`. Nothing here touches the main clone, the
hosts or the runtime on this Mac except the read-only `status` / doctor run in the checkpoint.

Found while planning (read-only, 2026-10-23):
- The test runtimes in `test_doctor.py` and `test_native_collaboration_runtime.py` write a vendored manifest with
  `tree = bridge_tree(BRIDGE_SOURCE)` but no `UPSTREAM.sha256` in the runtime directory, so they take the fallback of
  D249 and stay `current` unchanged; the new cases add a runtime `UPSTREAM.sha256` themselves.
- `test_runtime_upgrade.py` starts from a legacy git runtime; its "current runtime is left alone" case runs after a real
  (faked-build) upgrade, so it keeps passing; the new test-only case needs a vendored runtime whose list differs from
  the plugin's in one test line.
- The first committed `UPSTREAM.sha256` (483756c) hashes to `UPSTREAM_TREE`; its runtime mark becomes the legacy
  constant, checked by a test against a fixture copy of that list.

## Task List

### Task 1: the runtime mark (D248; assumptions 1, 2; requirements 1, 4)
Red first, in `test_bridge_vendoring.py`: every path in the plugin's `UPSTREAM.sha256` is in exactly one of
`RUNTIME_FILES` / `NOT_RUNTIME_FILES` (prefix `src/`, `test/`, `docs/` plus the exact names); the mark of a list is
unchanged when a `test/`, `docs/`, `README.md`, `CHANGELOG.md`, `INSTRUCTIONS.md`, `LICENSE`, `.gitignore` or
`tsconfig.test.json` line changes, and changes when a `src/`, `package.json`, `package-lock.json`, `tsconfig.json` or
`scripts/build.mjs` line changes; the legacy constant equals the mark of a fixture copy of the 483756c list, whose
whole-list hash is `UPSTREAM_TREE`. Green: the two constants, `runtime_mark(directory)` and the legacy constant in
`native_collaboration_runtime.py`. Verification: the new tests and the existing `test_bridge_vendoring` pass.

### Task 2: status judges by the runtime mark (D248, D249; assumptions 4, 5; requirement 2)
Red first, in `test_native_collaboration_runtime.py`: a vendored runtime whose own `UPSTREAM.sha256` hashes to the
manifest `tree` and differs from the plugin's only in a test line → `bridge` = `{"source": "vendored", "tree": <its
tree>, "current": true}`; differing in a `src/` line → `current: false`; runtime `UPSTREAM.sha256` missing, or not
hashing to `tree` → whole-list rule (current exactly when `tree` equals the plugin's); legacy `{"commit": …}` →
current exactly when the plugin's mark equals the legacy constant (patched both ways); the existing D26 status case
unchanged. Green: `_status` in `native_collaboration_runtime.py`; manifest writing untouched.

### Task 3: upgrade and doctor (assumptions 6, 7; requirement 3; AJM8B1H item 5)
Red first: `test_runtime_upgrade.py` — on a vendored runtime with a test-only difference `upgrade_runtime` returns
`state: "current"`, makes no backup, no stage and no build call; `test_doctor.py` — `runtime` is `ok` for a test-only
difference and `warn` for a `src/` difference, with the reworded detail ("the runtime's bridge files are older than
this plugin's") and the same upgrade advice. Green: the detail string in `native_collaboration_doctor.py` `_runtime`;
`upgrade_runtime` is expected to need no change.

### Task 4: docs (D250; assumption 8; requirement 5)
`RELEASING.md` lines 28–29 (release-note rule keyed to the bridge's runtime files) and 35–37 (a test- or doc-only bridge
change needs no runtime upgrade, but still runs `scripts/bridge-manifest.py` and gets an `UPSTREAM.md` line);
CHANGELOG `[Unreleased]`; README.md / README.en.md "升级" and `collaboration-ops` only where "equals the plugin's copy"
would now be wrong (expected: "same runtime files as the plugin's copy"). The spec's D26 text in
`spec/bridge-vendoring.md` is history and is not edited; `spec/runtime-mark-scope.md` D248 records the narrowing.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 (Node 24 first on PATH). Read-only on this Mac, from this
worktree: `native_collaboration_runtime.py status` (expected `current: true`, `tree` `442c21b7…`) and doctor's `runtime`
check (expected `ok`); results recorded in the todo.

### Task 5: PR and CI
Push, open the PR (Chinese title and body; links PA0EGGT and AJM8B1H item 5); the four CI jobs green; tell the owner
session the PR number; add a ledger comment on PA0EGGT and on AJM8B1H (item 5 handled here).

### Checkpoint (gate): module review
The owner session's review; the user merges. Release (patch) and the upgrade on this Mac are separate steps, asked of
the user by the owner session.
