# Spec: mailbox-core

## Objective

Make the extracted mailbox and native transport agent-relay's own: the private same-Mac runtime (pinned
upstream bridge), the Claude Code and Codex host adapters, identity retirement, and their skill, command, and
reference text. Behavior stays identical to the pre-split baseline; the only change is decision D1 naming
(MCP server name and state root), which the interface document already records as an approved naming difference.

Readers: the user reviewing the split; agents building `session-routing`, `cross-host-delegation`, `packaging`,
and `state-migration`, which build on these names.

Sources: [the interface document](../docs/collaboration-interface.md) §2, §4–§8, §13 (D1);
[the pre-split baseline](../docs/baselines/collaboration-pre-split.md); this repository's
[capability map](CAPABILITY-MAP.md).

## Assumptions

Confirmed by the user on 2026-10-07:

1. **Scope is the mailbox files only:** `hooks/native_collaboration_{runtime,adapters,retire}.py`,
   `hooks/host_config_removal.py`, `skills/collab/`, `skills/collaboration-ops/`, `commands/collaboration.md`,
   `references/collaboration-{runtime,protocol}.md`, and their tests. Routing and delegation names
   (`spec-guard-bridge` transport label, `spec-guard-result` markers, `<spec-guard-control>` tags,
   `spec_guard_delegation` private server, the delegation state root) are renamed by `session-routing` and
   `cross-host-delegation`; until then they keep working because delegation imports the server name from the
   adapters.
2. **Names (D1, already approved):** Claude MCP server `agent-relay`, Codex table `[mcp_servers.agent_relay]`,
   Claude permission rules `mcp__agent-relay__bridge_*`; the ten `bridge_*` tool names and the denied-tool list
   are unchanged. The probe's MCP client name becomes `agent-relay-probe`.
3. **File names stay** (`native_collaboration_*.py`, skill directory names `collab`, `collaboration-ops`): Spec
   Guard and the interface refer to `agent-relay:collab`, and renaming files adds churn without behavior.
4. **Text says agent-relay, not Spec Guard.** Skills, command, references, docstrings, and error messages are
   reworded; commands in them use `plugins/agent-relay/…` paths and resolve the installed agent-relay root
   (Claude `CLAUDE_PLUGIN_ROOT`, Codex `codex plugin list --json` entry named `agent-relay`). The slash command
   becomes `/agent-relay:collaboration` by the plugin name; its file stays `commands/collaboration.md`.
5. **Two mailboxes may coexist until `state-migration`.** The installed Spec Guard 0.49.0 keeps its own runtime at
   `~/.spec-guard/native-collaboration/`; agent-relay installs a separate one. Identities in one are not visible in
   the other. This is expected and documented; nothing in this module reads or writes the old root.
6. **Verification is unit tests plus one scratch install.** Real host adapter installs (writing `~/.claude.json`
   or `~/.codex/config.toml`) are not done here; they happen in the acceptance run after all translation modules.
   One `install` + `probe` into a scratch root checks the renamed runtime against the real pinned bridge (needs
   network for `git fetch` and `npm ci`; approval asked at Plan review).

## Decisions

Taken as recommended by the user on 2026-10-07.

- **D9 state layout.** `install_runtime` refuses an existing root and creates only its parent, so agent-relay
  cannot use `~/.agent-relay/` itself as the runtime root once delegation records or migration backups live
  there. Decision: keep the old shape with a new parent —
  `~/.agent-relay/runtime/` (was `~/.spec-guard/native-collaboration/`),
  `~/.agent-relay/delegation/` (was `~/.spec-guard/session-delegation/`, moved by `cross-host-delegation`),
  `~/.agent-relay/backups/` (created by `state-migration`). The parent is created owner-only (0700) as today.
  Interface §13 says "new root `~/.agent-relay/`"; this refines it, and the interface row is updated to the
  sub-paths in this module.

## Requirements

1. `default_root()` returns `~/.agent-relay/runtime`; `install_runtime` creates `~/.agent-relay` (0700) when
   absent and the root is the default, exactly as it does for `~/.spec-guard` today.
2. `CLAUDE_SERVER_NAME = "agent-relay"`, `CODEX_SERVER_NAME = "agent_relay"`; Claude deny rules, Codex
   `enabled_tools`, exact-match removal, and uninstall use the new names; byte-for-byte removal semantics unchanged.
3. Probe client name `agent-relay-probe`.
4. Skill, command, and reference text per assumption 4; every command shown in them runs from an installed
   agent-relay root.
5. Interface document §13 rows for the mailbox and delegation paths updated to D9; §2 and §13 server names already
   match D1 and are checked.
6. Tests: assertions that pin the old names or paths move to the new ones; no assertion is removed; total test
   count unchanged (215).
7. A name scan: no `spec-guard`, `spec_guard`, `Spec Guard`, or `.spec-guard` remains in the mailbox files of
   assumption 1, except where text explicitly describes Spec Guard history or the old state that
   `state-migration` will move (each such line listed in todo.md).

## Commands

```bash
/bin/bash scripts/validate.sh
python3 -B plugins/agent-relay/hooks/native_collaboration_runtime.py status
python3 -B plugins/agent-relay/hooks/native_collaboration_runtime.py install --root <scratch>/runtime
python3 -B plugins/agent-relay/hooks/native_collaboration_runtime.py probe --root <scratch>/runtime
```

## Project structure

Changed only: the files in assumption 1, `docs/collaboration-interface.md` §13, and `tasks/mailbox-core/`.

## Testing strategy

- Unit: `scripts/validate.sh` green with 215 tests after the rename; a test asserts `default_root()` is
  `~/.agent-relay/runtime` and that a default install creates the parent 0700.
- Name scan (requirement 7) recorded in todo.md.
- Scratch install and probe report `ready` with ten tools; the scratch root is deleted afterwards.
- Baseline comparison: messaging behavior is covered by the existing unit tests; the real-host comparison is
  checklist sections A–B in the acceptance run after all translation modules.

## Boundaries

- Always: change names and text only; keep every behavior and file mode; keep tests' meaning.
- Ask first: renaming files or skills; touching routing or delegation code; writing any host configuration;
  the scratch install (network).
- Never: read or modify `~/.spec-guard/`; write `~/.claude.json`, `~/.claude/settings*.json`, or
  `~/.codex/config.toml`; push the repository.

## Success criteria

1. `scripts/validate.sh` green, 215 tests.
2. Name scan clean apart from listed history lines.
3. Scratch install and probe `ready`. (Correction at build: probe reports `toolCount` 17, every tool the pinned
   server registers, each either allowed (ten) or denied (seven); the ten-tool allow list is what the host
   adapters expose. "Ten tools" in the testing strategy meant the allow list.)
4. Interface §13 matches D9.

## Open questions

None; D9 is decided.
