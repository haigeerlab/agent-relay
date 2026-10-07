# Plan: bridge-vendoring

Based on [`spec/bridge-vendoring.md`](../../spec/bridge-vendoring.md) (accepted by the user on 2026-10-07: location
`plugins/agent-relay/bridge/`, left-out list, D23–D25). Branch `claude/bridge-vendoring` from main 9b1b3fa.

## Overview

Copy the files and record their provenance first (and prove them identical to upstream), then switch the installer to
the copy with verification, then docs, then the live build-identity check.

## Architecture Decisions

- Files are taken from the local runtime's git object store at `8f12c88` (`git -C ~/.agent-relay/runtime show
  8f12c88:<path>`, read-only), so the copy is the committed blob, not a working-tree file.
- `UPSTREAM.sha256` uses `shasum -a 256` format, paths relative to `bridge/`, sorted; it excludes itself and
  `UPSTREAM.md`. One Python helper reads it for both the install check and the tree test.
- The installer copies with `shutil.copytree(..., ignore=node_modules, dist)` into the stage and verifies the stage,
  so what is built is what was checked.
- Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: Vendor the bridge and record provenance (D23, D25a)

**Description:** Write the assumption 2 file set from `8f12c88` blobs into `plugins/agent-relay/bridge/`; add
`UPSTREAM.md` and `UPSTREAM.sha256`; a test checks the tree against the manifest (no extra, missing or changed file).
Record D25a: every vendored file's `git hash-object` equals the blob at `8f12c88`.

**Acceptance:** spec requirements 1 and 3, D25a. **Verify:** `validate.sh`; mutation: edit one vendored byte → tree
test red. **Files:** `plugins/agent-relay/bridge/**`, new `hooks/test_bridge_vendoring.py`.

### Task 2: Install from the vendored copy (D24)

**Description:** `install_runtime` copies `bridge/` into the stage, verifies it against `UPSTREAM.sha256`, then runs
the same `npm ci` and build; no `git`. New installs write the D26 manifest; `status` accepts legacy and vendored
manifests and reports `bridge` {source, tree, current}. Tests with a fixture bridge and stubbed `npm`: success, manifest unchanged,
no `git` call; changed / extra / missing file each refused with nothing installed.

**Acceptance:** spec requirement 2. **Verify:** `validate.sh`; mutation: skip the check → tamper tests red.
**Files:** `native_collaboration_runtime.py`, `test_native_collaboration_runtime.py`.

### Checkpoint (report): installer uses the verified copy

### Task 3: Docs

**Description:** README credit and install text, `collaboration-ops` skill (no `git`), interface (citations resolve
in-repo, §13 note).

**Acceptance:** spec requirement 5. **Files:** `README.md`, `skills/collaboration-ops/SKILL.md`,
`docs/collaboration-interface.md`.

### Task 4: Live identity proof (D25b–d; round 1 owner told first)

**Description:** Temporary `AGENT_RELAY_HOME`: `install` from the copy; compare its `dist/` with
`~/.agent-relay/runtime/dist` byte for byte; run upstream `npm test` in a built copy under the scratchpad; `probe`
ready with 17 tools; `npm ls --all --json` equal to the current runtime's; record the upstream test count; remove everything; real root and host config unchanged.

**Acceptance:** spec success criterion 2. **Files:** `tasks/bridge-vendoring/todo.md`.

### Checkpoint (gate): module review
