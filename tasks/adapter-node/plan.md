# Plan: adapter-node

Based on [`spec/adapter-node.md`](../../spec/adapter-node.md) (accepted by the user on 2026-10-08: assumptions 1–4,
D58). Branch `claude/adapter-node` from main feaa0e8. Red → green.

## Task List

### Task 1: Adapters select the node (D58)
`--node` loses its default. Before the backup: `codex`, `claude`, `install-codex`, `install-claude` call
`select_node(args.node)` and on `NodeSelectError` exit non-zero with `reason: detail`, nothing written;
`uninstall-codex` tries `select_node` and falls back to PATH's node (or the fragment's own command) without refusing.
Tests in a new `hooks/test_adapter_node.py` with fake v12 first on PATH and a fake v24 pinned in a temporary
`.claude.json`: install-codex writes v24; codex/claude print v24; only v12 → refusal, config and backups unchanged;
explicit old `--node` refuses; uninstall-codex under only v12 removes a v24 table.
**Files:** `hooks/native_collaboration_adapters.py`, new test.

### Task 2: Docs
README node paragraph adds the host adapters.

### Task 3: Live (temporary HOME, coordinator told first)
nvm v12 first, `/usr/bin/python3`: install-codex with a v24 Claude entry writes v24; with no entry refuses and writes
nothing; uninstall-codex removes the table.

### Checkpoint (gate): module review
