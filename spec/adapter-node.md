# Spec: adapter-node

## Objective

The host adapters write the node the host entries pin, never PATH's first one (round 2 acceptance-kit run, R2-13):
`install-codex`, `install-claude` and the printing commands `codex` and `claude` choose their node with D50's
`select_node` and refuse a node below 22.5.0 before anything is written.

Readers: the user; the round 2 coordinator ("第二轮联调"), who found R2-13 and re-runs it.

## What exists today (measured, main feaa0e8, 2026-10-08)

- `native_collaboration_adapters.py` line 205: `--node` defaults to `shutil.which("node")`. `codex`, `claude`,
  `install-codex`, `install-claude` and `uninstall-codex` build their fragment with it; `uninstall-claude` uses no
  node. The host-file backup runs before the node is checked.
- Coordinator's reproduction: nvm v12 first in PATH, `~/.claude.json` entry pinning v24,
  `install-codex --codex-config <temp file>` → rc 0 and `command = ".../v12.22.12/bin/node"` written.
  `uninstall-codex` under v12 removes a table written with v24 (safe-uninstall accepts another absolute node path).

## Assumptions

Confirmed by the user on 2026-10-08.

1. `codex`, `claude`, `install-codex`, `install-claude` use `select_node(--node)` (`--node` → Claude entry → Codex
   table → PATH); `node-too-old` (with the `node:sqlite` reason) refuses before the backup and before any host write.
2. `uninstall-codex` never refuses on the node: it uses the selected node for the comparison fragment and falls back to
   PATH's node when selection refuses, so an old node cannot block removal.
3. `uninstall-claude` is unchanged.
4. When re-attaching after an uninstall the Claude entry may be gone; selection falls through to the Codex table and
   PATH as usual and still checks the version.

## Decisions

- **D58 adapters choose the node like everything else (R2-13).** As assumptions 1–4. Accepted on 2026-10-08.

## Requirements

1. Tests, in a shell with v12 first on PATH (fake nodes): the pinned v24 is written by `install-codex` and printed by
   `codex`/`claude` without `--node`; only v12 → `node-too-old`, exit non-zero, host file and backups directory
   unchanged; an explicit too-old `--node` refuses too; `uninstall-codex` with only v12 still removes a v24 table.
2. Live in a temporary HOME with nvm v12 first and `/usr/bin/python3` 3.9: the same three cases.
3. README node paragraph names the adapters.

## Boundaries

- Always: refuse before any write; keep uninstall possible.
- Ask first: real host files.
- Never: push without approval.

## Success criteria

Tests green on Python 3.9, 3.10, 3.14; live check passes; the coordinator's R2-13 reproduction writes v24.

## Open questions

None.
