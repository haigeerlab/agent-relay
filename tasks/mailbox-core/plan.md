# Plan: mailbox-core

Based on [`spec/mailbox-core.md`](../../spec/mailbox-core.md) (reviewed by the user on 2026-10-07, D9 accepted).
Repository `/Users/vilin/Documents/haigeerlab/agent-relay`, branch `main`, local only. Reread
[`docs/collaboration-split-brief.md`](../../docs/collaboration-split-brief.md) after any context reset.

## Overview

Rename in code first (names, root, probe client) with the tests that pin them, then reword the skill, command, and
reference text, then update the interface rows and prove the runtime with one scratch install.

## Architecture Decisions

- **Names live in one place each:** `CLAUDE_SERVER_NAME`, `CODEX_SERVER_NAME`, `default_root()`. Delegation and the
  acceptance helpers already import them, so they follow without edits.
- **Tests change only where they pin old names or paths;** each changed assertion keeps its meaning. The count
  stays 215.
- **Scratch install** goes to the session scratchpad with an explicit `--root`; it never touches `~/.agent-relay`.
- Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: Code names and state root

**Description:** `default_root()` → `~/.agent-relay/runtime`; parent creation stays 0700 for the default root;
server names `agent-relay` / `agent_relay`; probe client `agent-relay-probe`; `host_config_removal.py` docstring
and error text say agent-relay. Update the mailbox tests that pin these; add one test for the default root and
parent mode if none covers it.

**Acceptance:** 215 tests (or 216 with the new root test) green; `runtime.py status` on this Mac reports `absent`
for `~/.agent-relay/runtime`.

**Verify:** `scripts/validate.sh`; one `status` run.

**Files:** `hooks/native_collaboration_runtime.py`, `hooks/native_collaboration_adapters.py`,
`hooks/host_config_removal.py`, mailbox tests

### Task 2: Skill, command, and reference text

**Description:** Reword `skills/collab/SKILL.md`, `skills/collaboration-ops/SKILL.md`, `commands/collaboration.md`,
`references/collaboration-runtime.md`, `references/collaboration-protocol.md`: agent-relay instead of Spec Guard,
`plugins/agent-relay/…` command paths, root resolution by the `agent-relay` plugin name, new state paths and
permission rule names. Update the entry-contract tests that pin the old wording.

**Acceptance:** runner green; name scan of the Spec's mailbox files clean except listed history lines.

**Verify:** `scripts/validate.sh`; the name scan recorded in todo.md.

**Files:** the five text files, `hooks/test_collab_entry.py`, `hooks/test_native_collab_entry.py`, other entry tests
if they pin wording

### Checkpoint (report): names and text translated, tests green

### Task 3: Interface rows and scratch install

**Description:** Update `docs/collaboration-interface.md` §13 mailbox and delegation rows to the D9 sub-paths.
Run `install --root <scratch>/runtime` then `probe --root <scratch>/runtime` with the real pinned bridge; record
the result; delete the scratch root.

**Acceptance:** probe `ready` with ten tools; interface §13 matches D9.

**Verify:** the two command outputs in todo.md; runner green.

**Files:** `docs/collaboration-interface.md`, `tasks/mailbox-core/todo.md`

### Checkpoint (gate): module review

Stop and report per the brief format, with the baseline comparison (tests, names, probe). Never pushed.

## Risks

- Entry-contract tests may pin Spec Guard phrases in ways that make the rename touch many assertions; each is
  moved, not dropped, and listed at the checkpoint.
- The scratch install needs network and Node.js ≥ 22.5; if either is missing the task stops and reports instead of
  skipping the probe.
