# Spec: acceptance-kit-round2

## Objective

Close the gaps integration round 2 found in the acceptance kit and in how agent-relay's skills find their own code
([record](../docs/acceptance/2026-10-07-round2.md)): the printed background-session launch line keeps its prompt
(R2-3); preflight shows when a host runs a stale copy of the plugin (R2-5) and the skills never pick a stale copy
when they resolve the plugin root (R2-11); the A4 allow list covers the skills the checklist exercises (R2-8); and
reinstall, retire and the acceptance cleanup work in a shell whose first node is too old and whose `python3` is the
system 3.9 (R2-12, found in the coordinator's fc7ee7e re-run, added to this module by the user on 2026-10-08).

Readers: the user; the integration coordinator ("第二轮联调"), who runs the third round with this kit.

## What exists today (measured, main fc7ee7e and this Mac read only, 2026-10-07)

- **R2-3.** `scripts/acceptance/preflight.sh` prints `claude --bg --permission-mode dontAsk --allowedTools "<list>"`.
  `--allowedTools` is variadic (Claude Code 2.1.291), so a prompt appended after it is read as a tool name and the
  session starts idle.
- **R2-11.** `collaboration-ops`, `session-delegation` and `session-routing` say in prose "resolve the installed
  agent-relay root as `$ROOT` (Claude: `CLAUDE_PLUGIN_ROOT`; Codex: `source.path`)". Nothing is substituted, so an
  agent looks for the root itself. `~/.claude/plugins/installed_plugins.json` holds seven agent-relay records (user and
  several local scopes, commits 5cdd8a5 … ef77d7f), every `installPath` the same version-keyed cache
  `~/.claude/plugins/cache/agent-relay-marketplace/agent-relay/0.1.0`; the marketplace is `source: directory` (the main
  checkout), from which, per the coordinator's round 2 re-run, Claude loads the plugin. Spec Guard's skills instead
  write `ROOT="${CLAUDE_PLUGIN_ROOT}"`, which Claude Code substitutes at load (this session shows its spec-guard skills
  with the 0.50.1 cache it loaded, while the record already says 0.51.2), then fall back to `codex plugin list --json`
  `source.path`, then refuse. Docs: `${CLAUDE_PLUGIN_ROOT}` is a skill string substitution
  (code.claude.com/docs/en/skills.md); which directory it names for a `directory` marketplace is not documented.
- **R2-5.** preflight prints Claude's install records and Codex's `source.path`, never the copy Codex runs
  (`~/.codex/plugins/cache/agent-relay-marketplace/agent-relay/<version>`), so round 2 ran a round-1-era Codex copy
  unnoticed.
- **R2-8.** The A4 list is `ListAgents,SendMessage` plus the ten mailbox tools. `session-routing` needs
  `python3 -B <root>/hooks/session_routing.py select` through Bash before any send, and a D9 receiver reads a file in
  the design project; neither is allowed, so Claude-origin D8 and S4's D9 read stopped. Rule syntax per
  code.claude.com/docs/en/permissions.md: absolute paths are `Read(//abs/path/**)`; Bash prefixes are
  `Bash(<prefix> *)`.

- **R2-12.** (1) `native_collaboration_runtime.py install`/`upgrade` run `npm ci` and `npm run build` with `--npm`
  (default `npm`) and `--node` (default `node`); npm starts through `#!/usr/bin/env node`, so with nvm v12 first in
  PATH the build fails even with `--npm <v24 npm>` (nothing replaced). (2) `native_collaboration_retire.py --node`
  defaults to `shutil.which("node")`. (3) `scripts/acceptance/cleanup.sh` opens the mailbox with `mode=ro` directly,
  which fails under `/usr/bin/python3` 3.9 exactly as R2-9 did.

## Assumptions

Confirmed by the user on 2026-10-07.

1. R2-11 is a product defect: the three skills resolve the root the way Spec Guard's do — `${CLAUDE_PLUGIN_ROOT}`
   substituted by Claude, else the enabled `source.path` from `codex plugin list --json`, else a clear refusal —
   and never read `installed_plugins.json` or guess a cache directory.
2. Claude substitutes `${CLAUDE_PLUGIN_ROOT}` with the copy the session actually loaded; verified by a live probe
   before the skills depend on it (Task 1).
3. preflight compares the source tree with each host's copy by a file-tree hash, ignoring host-generated entries
   (Codex `migrated-command-skills`) and `node_modules`; a difference is reported `STALE` with the refresh command.
   Read only.
4. preflight prints two allow lists: base (mailbox tools, ListAgents, SendMessage) and routing (base plus the
   selector's Bash rule and the D9 design-project Read rule); the checklist names which rows use which.
5. The printed launch line is `claude "<prompt>" --bg …`.

## Decisions

D53–D56 accepted on 2026-10-07 (including D53's Task 1 fallback and the `--design` option, approved at spec review).

- **D53 root resolution (R2-11).** One shell block, identical in the three skills: `ROOT="${CLAUDE_PLUGIN_ROOT}"`;
  if empty or not a directory holding `hooks/native_collaboration_runtime.py`, the enabled agent-relay `source.path`
  from `codex plugin list --json`; else stop with "cannot locate the agent-relay plugin root" and the reason. A test
  pins the block in all three and forbids `installed_plugins.json` and `plugins/cache` in skill text. If Task 1 shows
  Claude substitutes a stale cache for a `directory` marketplace, the block also compares that root's tree hash with
  the source and refuses on a mismatch (decided at Task 1, reported to the user before building on it).
- **D54 stale copies (R2-5, R2-11).** preflight prints, per host, the copy in use and its tree hash next to the
  source's: Claude — each `installed_plugins.json` record's `installPath` (marked as the record, not proof of what a
  session loads); Codex — the cache under `~/.codex/plugins/cache/agent-relay-marketplace/agent-relay/`. Mismatch →
  `STALE` plus the host's refresh command (`claude plugin install …` / `codex plugin add …`), run only by the user.
- **D55 allow lists (R2-8).** `base` and `routing` lists printed with the exact rules
  (`Bash(python3 -B <root>/hooks/session_routing.py select *)`, `Read(//<design project>/**)` from a new `--design <path>` option,
  omitted with a note when not given). Checklist A4, D8, D9 name the list to use.
- **D56 launch line (R2-3).** `claude "<prompt>" --bg --permission-mode dontAsk --allowedTools "<list>"`, with a note
  that the prompt must come first; checklist A4 matches.

- **D57 the same node and the same read everywhere (R2-12).** `install`, `upgrade` (and the reinstall around kept
  history) and `retire` choose their node with D50's `select_node` (explicit `--node` → Claude entry → Codex entry →
  PATH; below 22.5.0 refuse before anything is built or retired). npm runs with the chosen node's directory first in
  its `PATH`, and `--npm` defaults to the `npm` beside that node when present (else PATH's). `cleanup.sh` reads the
  mailbox with D51's `open_mailbox_read_only`. Acceptance: in a shell with nvm v12 first in PATH and `python3` =
  `/usr/bin/python3` 3.9.6, reinstall around kept history, retire and `cleanup.sh` all succeed.

## Requirements

1. D53: the shared block in three skills, tested; Task 1 probe recorded.
2. D54: tree hash function tested on fixtures (equal, changed file, ignored entries); preflight output shows
   `current`/`STALE` per copy.
3. D55, D56: preflight output tested for exact strings; checklist rows updated.
4. D57: npm environment and node choice tested with fake node/npm scripts; retire's default tested; cleanup.sh on a
   closed WAL mailbox under 3.9.
5. Round 2 record cross-references (R2-3, R2-5, R2-8, R2-11, R2-12).

## Testing strategy

Python tests drive preflight's helpers with fixture homes (fake `installed_plugins.json`, fake Codex cache, fake
`codex` CLI). Live: the Task 1 probe (a fresh Claude session reports what a test skill's `${CLAUDE_PLUGIN_ROOT}`
became — needs the user's agreement since it loads a plugin version in a real session), and preflight run read only
on this Mac (it already reads the real host records; nothing written).

## Boundaries

- Always: read only in preflight; never refresh a host's plugin copy for the user.
- Ask first: the Task 1 probe on the real host; any change to host plugin records.
- Never: edit `installed_plugins.json` or Codex caches; push without approval.

## Out of scope

R2-2, R2-4 (observations); cleaning stale install records (the host's).

## Success criteria

1. Tests green on Python 3.9, 3.10, 3.14.
2. preflight on this Mac names every stale copy.
3. The coordinator's third round starts with this kit.

## Open questions

Which directory `${CLAUDE_PLUGIN_ROOT}` names for a `directory` marketplace (Task 1).
