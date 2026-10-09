# Spec: install-docs-accuracy

## Objective

Last module of 0.6.1: what agent-relay tells the user must match what it does. From the round-2 coordinator's
post-release review of 0.6.0 (items 3, 4, 5c, 5d, 5h) and the user's decision of 2026-10-09: Codex installation keeps
writing `approval_mode = "approve"` for the ten mailbox tools (`native_collaboration_adapters.py:98`), but install and
upgrade must say exactly which rules they write. The module ends with the 0.6.1 CHANGELOG.

Readers: the user; people installing agent-relay from the README; the round-2 coordinator.

## What exists today (main 835304b, v0.6.0)

- **Approvals.** `install-codex` prints only "Native Codex MCP configuration installed; restart Codex to load it.";
  `--approve-mailbox-tools` adds missing approvals; neither lists the ten `[mcp_servers.agent-relay.tools.<tool>]`
  tables it writes.
- **Item 3.** `collab/SKILL.md:27` says any permission mode can bind wake, while `BACKGROUND-WAKE.md` ("Why Claude pings
  expire") says a Bypass-permissions Claude session holds cross-session messages for approval and, in the desktop app,
  lets them expire unless `crossSessionInbound` is `"accept"`.
- **Item 4.** README commands use the repository path `plugins/agent-relay/hooks/…` (e.g. lines 78, 160–161); a user who
  installed the plugin has no such directory. The collab skill gives no path at all.
- **5c.** Two messages say agent-relay "never edits" `~/.claude/settings.json` / permission files
  (`native_collaboration_adapters.py:208`, `state_migration.py:498`), but `uninstall-claude` runs
  `remove_claude_deny_rules`, which removes the deny rules 0.4.0 wrote there.
- **5d.** `session-routing/SKILL.md:19` shows `printf '%s' '<json>' | python3 …`; a name or title with an apostrophe
  breaks the single quotes. The pipe itself is right (A7, guarded by `test_selector_json_is_piped_not_a_heredoc`).
- **5h.** The 2.0 breaking-change summary in CHANGELOG does not list the removal of `--host-permission`.

## Assumptions (to be confirmed by the user)

1. **Approvals are stated.** `install-codex` (and `--approve-mailbox-tools`, and README/collaboration-ops upgrade steps)
   print the ten tool names and the exact table form written to `~/.codex/config.toml`, before the restart hint; the
   README install section says the same. Behaviour does not change.
2. **Bypass caveat.** collab skill and README: binding works in any mode, but a Claude session in Bypass permissions
   holds incoming pings for approval (the desktop app lets them expire) unless the user sets `crossSessionInbound`;
   link to `BACKGROUND-WAKE.md`. No setting is changed for the user.
3. **Installed paths.** README commands use `<插件目录>` with one short subsection showing how to find it on each host
   (Claude Code: the plugin path shown by `claude plugin list`, or the cache path for a GitHub install; Codex: the
   "Installed plugin root" printed by `codex plugin add`). The exact commands are taken from this Mac, not from memory.
   The collab skill tells the agent to resolve the hooks directory from its own skill location.
4. **5c wording.** Both messages say what is true: agent-relay does not add allow rules to the user's settings; its
   uninstall removes only the deny rules 0.4.0 wrote.
5. **5d.** Keep the 0.6.0 form `printf '%s' <json> | python3 -B …/session_routing.py select` (a pipe, no heredoc —
   A7: a heredoc fails in Codex's read-only sandbox), so the documented allow rules still match. Only the quoting
   changes: the whole JSON is one argument quoted by `shlex.quote`'s rule — wrapped in single quotes, every `'` inside
   written as `'\''`. Inside single quotes bash and zsh expand nothing, so `$(…)`, backticks, `$HOME` and `!` in a name,
   title or body reach the selector verbatim; double quotes are never used for user text (they expand `$(…)`). The
   skill states this rule with one worked example. Reading the selector's input from separate arguments was considered
   and rejected: it changes the selector's interface and its allow rule for no gain over correct quoting.
6. **CHANGELOG.** `--host-permission` removal joins the 2.0 breaking list; a `[0.6.1]` entry lists the three modules,
   the upgrade from 0.6.0 (delegation store schema 2 → 3; runtime upgrade for `presence-polish`) and rollback (restore
   the delegation store copy).

## Decisions

- **D178 install states the approvals it writes.** Assumption 1 (user decision (2), 2026-10-09).
- **D179 documentation matches behaviour.** Assumptions 2–6.

## Requirements

1. Red first: `install-codex` output names all ten tools and the table form; `--approve-mailbox-tools` names the ones
   it added.
2. Red first (skill tests): collab mentions the Bypass hold and `crossSessionInbound`; session-routing states the
   single-quote rule and uses no heredoc (the existing heredoc guard stays green); a command built by that rule from a
   name and body containing `'`, `$(…)`, backticks and `$HOME`, run under both `bash` and `zsh`, hands the selector
   exactly the original text (nothing expanded or executed); README has no `plugins/agent-relay/hooks/` command outside the developer section.
3. The two "never edits" messages corrected; CHANGELOG `[0.6.1]`.
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Never: change the user's Claude or Codex settings to make these docs true; change the approvals behaviour.

## Acceptance (coordinator, after 0.6.1 — not done here)

- A long message with many escapes, read in parts: no part exceeds the host's output limit; find Codex's limit.
- Whether the documented `printf … | python3` (or its replacement) matches the existing allow rules on the real host.

## Open questions

None beyond the assumptions above.
