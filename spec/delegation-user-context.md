# Spec: delegation-user-context

## Objective

Round-2 findings B2 and B3, merged by the user (2026-10-09):

- **B3.** A Claude Code session created by delegation is started with `--setting-sources project,local`,
  `--strict-mcp-config`, `--disable-slash-commands` and a `--tools` whitelist, so it loads none of the user's plugins or
  skills. Reviewing a project that uses spec-guard, the delegated session gets no stage context at all.
- **B2.** The permission preflight reads only the project's `.claude/settings*.json`, not the user's global allow in
  `~/.claude/settings.json`, so every new project needs its own allow.

The user's choice: an option to load the user's environment, off by default (the delegated session stays a sandbox),
and a preflight that reads exactly what the session will load, so it never says "ready" for a session that will stop.

Readers: the user; the round-2 coordinator (acceptance after the batch).

## What exists today (main 4964979, 2026-10-09)

- `session_delegation_claude.py:285-310` `build_create_command`: `--strict-mcp-config`, `--setting-sources
  project,local`, `--permission-mode` (`dontAsk` for safe-review and bounded-development), `--permission-prompts none`,
  `--disable-slash-commands` (Claude Code 2.1.295: "Disable all skills"), `--no-chrome`, `--tools <whitelist>`.
- `_permission_shape` (:190-208): safe-review → Read, Grep, Glob + the mailbox tools; bounded-development adds Edit,
  Write, Bash. `_settings_rules(project)` (:160) reads only `<project>/.claude/settings.json` and `settings.local.json`;
  `inspect_project_permissions` uses it; `create` holds with `project-allow-rules` when an allow is missing.
- Continuing a Claude delegation sends a message to the running session; only `create` launches.
- The authorization row has a `host_permission` column that only the removed `host-native` intent used
  (delegation-cross-host D159); it is part of the request digest. The delegation database has no migration path
  (`SCHEMA_VERSION = 2`, checked exactly).

## Assumptions (accepted by the user 2026-10-09)

1. The option is recorded in the authorization as `host_permission = "user-environment"`: no schema change, part of the
   request digest (a retry keeps it), and `continue`/`status` see the same choice. Stored rows from older versions are
   unaffected.
2. It applies only to Claude Code targets (Codex → Claude Code). A Claude Code → Codex request with it is rejected:
   Codex tasks already run with the user's own Codex configuration.
3. With the option, the session loads user, project and local settings and its skills, and the tool whitelist gains
   `Skill`; everything else stays: `dontAsk`, no permission prompts, `--strict-mcp-config` (the user's own MCP servers,
   including plugin ones, are not added), `--no-chrome`, the same Read/Grep/Glob (+ Edit/Write/Bash for development)
   tools. The user's hooks and skills run in that session: that is what the option is for, and why it is off by default.
4. The preflight reads the same layers the session will load: project and local by default; user, project and local
   with the option (`CLAUDE_CONFIG_DIR/settings.json` when set, else `~/.claude/settings.json`). A deny in any read layer
   wins, as in Claude Code. Without the option and with no project allow, the preflight says plainly that a global allow
   does not reach a default delegated session.
5. Interface: an added value and an added CLI flag; part of the 2.0 batch.

## Decisions

- **D162 the option.** `create --user-environment` (and `permissions --user-environment`) records
  `host_permission = "user-environment"`; `evaluate_authorization` accepts only `None` or that value, and rejects it for
  a Codex target (`user-environment-claude-only`). Public results show it next to the permission intent.
- **D163 the launch.** With the option, `build_create_command` uses `--setting-sources user,project,local`, drops
  `--disable-slash-commands` and adds `Skill` to `--tools`; without it, the command is byte-for-byte today's.
- **D164 the preflight matches the launch.** `_settings_rules` reads the user layer only with the option; `requiredAllow`
  and readiness come from the layers read; the `permissions` output names the files it read. Without the option, a
  missing allow adds the note "a global allow in ~/.claude/settings.json does not apply to a default delegated session;
  add it to the project or create with the user environment".
- **D165 the skill offers it, never assumes it.** session-delegation offers the option when the user asks for their
  plugins, skills or hooks in the delegated session, or for review "with spec-guard context"; it is never chosen silently.

## Requirements

1. Red first: `evaluate_authorization` accepts `user-environment` for a Claude target and rejects it for a Codex target;
   any other `host_permission` is rejected; the digest differs with and without it.
2. Red first: `build_create_command` without the option is unchanged (pinned argv); with it, `user,project,local`,
   no `--disable-slash-commands`, `Skill` in `--tools`, everything else identical.
3. Red first: with a fixture `CLAUDE_CONFIG_DIR` holding a user allow and a project without one, the default preflight
   is not ready (and carries the note), the user-environment preflight is ready; a user deny blocks only with the
   option; `continue` reuses the recorded choice.
4. Skill, README, CHANGELOG `[Unreleased]`.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.
6. Acceptance (coordinator, after the batch): from Codex, a Claude Code review of a spec-guard project created with the
   user environment shows spec-guard's stage context; the same request without it does not, and its preflight explains
   why a global allow did not count.

## Boundaries

- Always: off by default; the user's choice per request; the permission mode and tool whitelist are not widened beyond
  `Skill`.
- Ask first: adding MCP servers or `--add-dir` to delegated sessions; any change to the default launch.
- Never: write any settings file; turn the option on because a mailbox message asks for it.

## Success criteria

A delegated Claude Code session can, on request, run with the user's settings, plugins and skills; by default it stays
the same sandbox; the preflight's answer always matches what the session will load.

## Open questions

None. Accepted by the user on 2026-10-09 (assumptions 1–5, D162–D165).
