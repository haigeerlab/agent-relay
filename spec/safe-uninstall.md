# Spec: safe-uninstall

## Objective

Make taking agent-relay off a Mac safe and complete: `uninstall-codex` removes its Codex table even after the user
chose 始终允许 for some tools (Codex then adds approval subtables), and names the exact lines when something else
differs; every write to host configuration — install and uninstall, Claude and Codex — keeps a copy of the file
first; and one documented procedure removes agent-relay from both hosts while the message history stays.
Round 1 report finding 6; interface gap k (§2.3 row 66, §13 rows 248, 249); checklist D17.

Readers: the user; the round 1 coordinator (D17 and round 2 cleanup); anyone uninstalling.

## What exists today (measured, main 49ef6ba and this Mac's Codex config read only, 2026-10-07)

- **Codex removal is exact-match** (`host_config_removal.remove_codex_table`): the file must contain the fragment
  `codex_fragment(root, node)` would write today as a complete table, and nothing else under
  `[mcp_servers.agent_relay…]`; otherwise "differs from what agent-relay installed; remove it manually" with only the
  table's first line number.
- **This Mac's `~/.codex/config.toml`** holds the exact fragment followed by five Codex-written subtables
  `[mcp_servers.agent_relay.tools.<tool>]` with the single line `approval_mode = "approve"` (bridge_register,
  bridge_inbox, bridge_agents, bridge_wait, bridge_ack) — so `uninstall-codex` refuses today (finding 6). The fragment
  also embeds the absolute node path (`~/.nvm/versions/node/v24.18.0/bin/node`); a different `--node` makes it
  differ too.
- **Host writes without a copy:** `install-codex` (rewrites `config.toml` atomically), `install-claude` (deny rules into
  `~/.claude/settings.json`, then `claude mcp add-json --scope user`, which writes `~/.claude.json`),
  `uninstall-claude` (`claude mcp remove --scope user`, `~/.claude.json`), `uninstall-codex` (`config.toml`). None keeps
  a backup (gap k). Round 1 made its own copies by hand in the scratchpad.
- **Uninstall leaves:** the seven Claude deny rules (kept on purpose: "harmless, effective on reinstall"); the runtime
  `~/.agent-relay/runtime/` (build, `mailbox/` with history and backups, `data/`). README §卸载 lists host entries →
  plugin → "history and runtime kept, delete yourself".

## Assumptions

Confirmed by the user on 2026-10-07.

1. **Approval subtables are Codex's, not the user's edits:** a table `[mcp_servers.agent_relay.tools.<name>]` whose only
   content is one `approval_mode = "<string>"` line (blank lines and comments allowed) is removed with the managed
   table. Any other content under `agent_relay` (an extra key, a different value in the fragment, a subtable with more
   keys) still refuses, and the message lists every differing line with its line number.
2. **The node path is matched as installed:** `uninstall-codex` compares against the fragment for the `command` actually
   in the table when that is the only difference and it is an absolute executable path — so a node upgrade does not
   strand the entry. (Alternative: keep requiring `--node`.)
3. **Backups:** before any host write the touched files are copied to `$AGENT_RELAY_HOME/backups/<UTC time>/host-config/`
   (directory 0700, files 0600, original names), and the command prints that path. Claude's CLI writes `~/.claude.json`,
   so that file is copied before calling it. A failed copy stops the write. Backups are never deleted automatically.
   The copies may hold credentials (MCP API keys, tokens): modes are set explicitly whatever the umask, the output
   says so, and contents are never logged.
4. **History stays:** nothing here deletes `mailbox/` or its backups.
5. `relay_status.py` output unchanged; `interface.json` 1.0; no bridge change.

## Decisions

D46–D48 accepted on 2026-10-07.

- **D46 deny rules on uninstall:** `uninstall-claude` also removes exactly the seven agent-relay deny rules (with the
  backup), because `install-claude` writes them again first, so keeping them protects nothing. Alternative: keep them
  (today's behaviour) and only document.
- **D47 the runtime on a complete uninstall:** a new `native_collaboration_runtime.py uninstall --confirm` refuses while
  a bridge server of this runtime runs, then removes only the build (`dist/`, `node_modules/`, sources, `manifest.json`)
  and keeps `mailbox/` (history, backups) and `data/`; `status` then reports `absent`-like `uninstalled` with the kept
  history path, and `install` can rebuild around the kept mailbox. Alternative: no command — the README tells the user
  which directory holds the history and that the rest may be deleted.
- **D48 order of the documented procedure:** close sessions → `doctor` → `uninstall-codex`, `uninstall-claude`
  (backups printed) → runtime (D47) → plugin removal per host → `doctor` shows not attached and no runtime build.

## Requirements

1. Approval subtables (assumption 1): this Mac's shape removed cleanly in a fixture; other differences refused with
   every differing line listed; quoted-name tables (`[mcp_servers."agent_relay".tools.x]`) handled as today.
2. Node path (assumption 2) tested.
3. Backups (assumption 3) for all four writes, tested: copy made before the write, path printed, modes, a failed copy
   stops the write, and a missing file is recorded as absent rather than failing.
4. D46 and D47 as decided, tested; D48 in the README and collaboration-ops skill.
5. Interface rows 66, 248, 249, gap k; checklist D17; round 1 report finding 6 cross-referenced.

## Testing strategy

Python tests with fixture homes and a fake `claude` binary (as existing adapter tests do). Live (temporary
`AGENT_RELAY_HOME` and a temporary HOME with copies of the host files, coordinator told first): install both hosts,
add the five approval subtables, uninstall both, check backups, `doctor` before and after. No change to the real host
files in this module; the real uninstall is the user's, in round 2 cleanup.

## Boundaries

- Always: copy before writing host config; keep history; remove only what agent-relay wrote (plus Codex's approval
  subtables for its own table).
- Ask first: touching the real host files; deleting anything under `mailbox/`.
- Never: edit lines the user changed; push without approval.

## Success criteria

1. All tests green; this Mac's subtable shape uninstalls in a fixture.
2. Live check passes; D17 target met in the temporary home.
3. Docs updated.

## Open questions

None.
