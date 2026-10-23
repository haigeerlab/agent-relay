# Spec: runtime-mark-scope

<!-- spec-guard: review pending -->

## Objective

Root-cause fix for a false "runtime is older" report (ledger PA0EGGT, plus item 5 of AJM8B1H). Requested by the user in
the owner session ("After 0.9.1"); ecosystem-lead says it does not change the interface and needs no further intake.
Planned as the next patch release.

The runtime's version mark is the SHA-256 of the whole `bridge/UPSTREAM.sha256` (bridge-vendoring D26). That file lists
every bridge file, tests and docs included. #154 changed only `bridge/test/identity.test.ts`, so the mark went from
`442c21b7` (0.9.0) to `9a293be0` (0.9.1): `status` reports `bridge.current: false`, doctor's `runtime` check warns
"runtime is ready but its bridge is older than this plugin's" and advises stopping every bridge for `upgrade --confirm`,
although the code the runtime builds and runs is byte-identical. The 0.9.1 CHANGELOG had to tell users to ignore that
advice; acceptance then noted that doctor's `next` still says "run upgrade --confirm" (AJM8B1H item 5).

This module makes "current" mean "the files the runtime is built from are the same", keeps the per-file integrity check
as it is, and lets every existing install use the new rule without reinstalling.

Readers: the user; the owner session (review, release, acceptance).

## What exists today (main 7bec33e, v0.9.1)

- `native_collaboration_runtime.py`: `bridge_tree(dir)` = SHA-256 of `dir/UPSTREAM.sha256`. `_build_runtime` writes
  `manifest.json` = `{"commit": BRIDGE_COMMIT, "source": "vendored", "tree": bridge_tree(stage)}`. `_status` accepts that
  shape or the legacy `{"commit": BRIDGE_COMMIT}` (git install) and sets `bridge.current` to
  `manifest.tree == bridge_tree(BRIDGE_SOURCE)`, or for the legacy shape `bridge_tree(BRIDGE_SOURCE) == UPSTREAM_TREE`
  (the hash of the unmodified 8f12c88 list, first committed in 483756c).
- `verify_bridge_copy` checks every file of a copy against `UPSTREAM.sha256` and refuses any changed, missing or extra
  file; `scripts/bridge-manifest.py` regenerates the list from all files except build outputs and the two provenance
  files.
- Readers of `bridge.current`: `upgrade_runtime` (returns `state: "current"` without doing anything when true; checks it
  after the swap), doctor `_runtime` (warn + "close the sessions using the mailbox, then run upgrade --confirm after the
  user agrees"), `scripts/acceptance/preflight.py` `runtime_bridge`, the collaboration-ops skill and README "升级".
- What the build reads (checked in the source): `npm ci --ignore-scripts` reads `package.json` and `package-lock.json`;
  `npm run build` runs `scripts/build.mjs`, which runs `tsc -p tsconfig.json` over `src/**/*.ts`. `INSTRUCTIONS.md` is
  not read at build or run time (the server's instructions are inline in `src/server.ts`).
- The installed runtime directory is the copied stage, so it keeps its own `UPSTREAM.sha256` and sources. Read-only on
  this Mac (2026-10-23): `~/.agent-relay/runtime/UPSTREAM.sha256` hashes to the manifest's `tree` (`442c21b7`).
- Computed from the release tags with the file set of assumption 1: 0.8.5 `0a6b2cad`, 0.9.0 `54540368`, 0.9.1
  `54540368` (whole-list marks: `9cdbf0b2`, `442c21b7`, `9a293be0`).

## Assumptions (confirmed by the user, 2026-10-23)

1. **Runtime files.** `src/**`, `package.json`, `package-lock.json`, `tsconfig.json`, `scripts/build.mjs`. Not runtime
   files: `test/**`, `tsconfig.test.json`, `docs/**`, `README.md`, `CHANGELOG.md`, `INSTRUCTIONS.md`, `LICENSE`,
   `.gitignore`. Both lists are constants; a test fails when `UPSTREAM.sha256` lists a path that is in neither, so a new
   build input cannot be left out silently.
2. **The runtime mark.** SHA-256 over the lines of an `UPSTREAM.sha256` whose path is a runtime file, in file order. It
   is used only for the comparison; it is not written to the manifest and not shown in `status`.
3. **Integrity check unchanged.** `verify_bridge_copy` still checks the whole tree file by file, and
   `bridge-manifest.py` still lists every file. A test or doc change still regenerates `UPSTREAM.sha256`.
4. **Existing installs.** The manifest format stays `{commit, source, tree}` (a new field would make an older plugin's
   `status` reject the manifest after a plugin rollback). For a vendored install, `status` reads the runtime's own
   `UPSTREAM.sha256`, checks that its SHA-256 equals the manifest's `tree`, computes its runtime mark and compares it with
   the plugin copy's. When that file is missing, unreadable or does not match `tree`, it falls back to today's rule
   (whole-list hashes equal); it never counts as current by default. A legacy git install compares against a constant:
   the runtime mark of the 8f12c88 list.
5. **Status output and interface unchanged.** `bridge.source`, `bridge.tree` (still the manifest's whole-list hash) and
   `bridge.current` keep their names, types and meaning; only `current` becomes true when the runtime files are the
   same. `interface.json` is not bumped.
6. **Upgrade follows.** With equal runtime files `upgrade --confirm` returns `state: "current"` and changes nothing (the
   existing early return; covered by a new test, no code change expected).
7. **Doctor wording (AJM8B1H item 5).** After the fix doctor warns only when the runtime files really differ, so the
   "upgrade --confirm" advice is right whenever it appears. The detail is reworded to say the runtime's bridge files are
   older than the plugin's. The 0.9.1 CHANGELOG entry is history and stays.
8. **RELEASING.md.** The release-note rule (lines 28–29) changes from "any change in the bridge directory" to "a change
   in the bridge's runtime files"; the paragraph at lines 35–37 says a test- or doc-only bridge change needs no runtime
   upgrade but still regenerates `UPSTREAM.sha256` and gets a line in `UPSTREAM.md`. CHANGELOG `[Unreleased]` gets an
   entry.
9. **Out of scope.** Bridge code, the manifest write format, the host and the runtime on this Mac.

## Decisions

- **D248 "current" compares runtime files only.** Assumptions 1, 2, 5, 6. Narrows the meaning of `current` in D26; the
  whole-list `tree` stays the recorded identity of an install.
- **D249 existing installs are judged from their own list.** Assumption 4. No migration and no manifest change.
- **D250 docs follow.** Assumptions 7, 8.

## Requirements

1. Red first (`test_bridge_vendoring.py` or `test_native_collaboration_runtime.py`): every path in the plugin's
   `UPSTREAM.sha256` is in exactly one of the two lists; the runtime mark ignores a changed test or doc line and changes
   with a changed `src/`, `package.json`, `package-lock.json`, `tsconfig.json` or `scripts/build.mjs` line.
2. Red first (status): a vendored install whose list differs from the plugin's only in a test line is `current: true`
   with `tree` unchanged; a difference in a runtime line is `current: false`; a runtime with its `UPSTREAM.sha256`
   missing, or not hashing to `tree`, uses the whole-list rule; the legacy git manifest is current exactly when the
   plugin's runtime mark equals the 8f12c88 constant.
3. Red first (upgrade, doctor): `upgrade_runtime` on a test-only difference returns `current` without touching the
   runtime or calling the build; doctor's `runtime` is `ok` for a test-only difference and `warn` with the reworded
   detail for a runtime difference.
4. The constant for the legacy mark is checked by a test against the list committed in 483756c (or the equivalent
   fixture), so it cannot drift.
5. RELEASING.md, CHANGELOG `[Unreleased]`; README and the collaboration-ops skill only if their wording of
   `bridge.current` ("equals the plugin's copy") needs a word changed.
6. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Ask first: anything on this Mac's runtime or hosts (none planned; acceptance after release is the owner session's).
- Never: changing what `verify_bridge_copy` refuses; writing a new manifest field; editing bridge code.

## Acceptance (owner session, after release)

- On this Mac, after updating the plugin to the release, doctor's `runtime` is `ok` without running `upgrade --confirm`
  (the installed 0.9.0 runtime has the same runtime files), and `status` still reports `tree` `442c21b7`.

## Open questions

None.
