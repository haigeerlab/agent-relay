# Plan: packaging

Based on [`spec/packaging.md`](../../spec/packaging.md) (reviewed by the user on 2026-10-07, scoped install plan
approved). Repository `/Users/vilin/Documents/haigeerlab/agent-relay`, branch `main`, local only. Reread
[`docs/collaboration-split-brief.md`](../../docs/collaboration-split-brief.md) after any context reset.

## Overview

Repository files first (interface marker, status command, manifests, README, tests), then the install
verification on both hosts with Spec Guard's probe, then Codex cleanup.

## Architecture Decisions

- `relay_status.py` reuses `native_collaboration_runtime.status()` (read-only); it adds no logic of its own beyond
  mapping `state == "ready"` to `ready: true` and printing the setup hint.
- The Spec Guard probe used for verification is the one in the Spec Guard worktree at the merged `main`
  (`/Users/vilin/Documents/haigeerlab/spec-guard-plugin/.claude/worktrees/cranky-allen-f2237a`, commit recorded),
  not the installed 0.49.0 (which predates the probe).
- Verification for every task: `/bin/bash scripts/validate.sh`.

## Task List

### Task 1: Interface marker, status command, manifests

**Description:** `plugins/agent-relay/interface.json`; `hooks/relay_status.py`; marketplace description;
`hooks/test_packaging.py` with: manifest consistency, `interface.json` shape (version `1.0`, status argv runs from
the plugin root), `relay_status` absent → `ready: false` + hint, ready → `ready: true`, no root created.

**Acceptance:** suite green; `claude plugin validate .` and `plugins/agent-relay` with no warnings.

**Verify:** `scripts/validate.sh`; both validators.

**Files:** `interface.json`, `hooks/relay_status.py`, `hooks/test_packaging.py`, `.claude-plugin/marketplace.json`

### Task 2: README and `.gitignore`

**Description:** Write `README.md` per Spec assumption 3; add the D8 phrase assertion to `test_packaging.py`;
`.gitignore` with `.claude/settings.local.json`.

**Acceptance:** every assumption-3 item present; phrase test green.

**Verify:** `scripts/validate.sh`; a section checklist in todo.md.

**Files:** `README.md`, `.gitignore`, `hooks/test_packaging.py`

### Checkpoint (gate): approve the host commands

Show exactly, before running:

```bash
# Claude, in /Users/vilin/Documents/haigeerlab/agent-relay (writes .claude/settings.local.json there)
claude plugin marketplace add /Users/vilin/Documents/haigeerlab/agent-relay --scope local
claude plugin install agent-relay@agent-relay-marketplace --scope local
# Codex (writes ~/.codex/config.toml; removed after verification)
codex plugin marketplace add /Users/vilin/Documents/haigeerlab/agent-relay
codex plugin add agent-relay@agent-relay-marketplace
```

### Task 3: Install verification and Codex cleanup

**Description:** Run the approved commands; record host versions; `claude plugin list` / `codex plugin list --json`
entries; the installed copies contain `skills/`, `commands/`, `interface.json`; Spec Guard's probe on both hosts
(expect `runtime-not-ready` with the setup hint). Then `codex plugin remove agent-relay@agent-relay-marketplace` and
`codex plugin marketplace remove agent-relay-marketplace`; confirm Codex no longer lists either; confirm Spec Guard
0.49.0 unchanged on both hosts.

**Acceptance:** Spec success criteria 1 and 3.

**Verify:** the recorded outputs in todo.md.

**Files:** `tasks/packaging/todo.md`

### Checkpoint (gate): module review

Stop and report per the brief format. Never pushed.

## Risks

- A local-scope Claude marketplace may not be visible to `claude plugin install` run from another directory; the
  commands are run from the agent-relay repository for that reason.
- If the probe reports `unknown` (for example the status command fails in the installed copy), that is a packaging
  defect to fix here, not a pass.
