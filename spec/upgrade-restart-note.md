# Spec: upgrade-restart-note

## Objective

The round-2 coordinator's E1 acceptance on 0.5.2 (2026-10-09, acceptance PR #47) found F2: when the bridges were
stopped with `pkill` for a runtime upgrade, the Codex threads that were already open in the ChatGPT app keep failing
their MCP calls with "Transport closed" until the ChatGPT app is quit and reopened. The upgrade notes only say "close
every session that uses the mailbox", so a user (or an agent) who stops the bridges with `pkill` is not told to
restart ChatGPT. The 0.5.2 upgrade also showed that `pkill -f "agent-relay/runtime/dist/server.js"` run from a shell
whose own command line contains that text kills that shell too; `pkill -f "[a]gent-relay/runtime/dist/server.js"`
does not. The user chose (2026-10-09) to document both. Docs only.

Readers: users upgrading the runtime; agents following the collaboration-ops skill; the round-2 coordinator, who
reviews the PR before the user merges.

## What exists today (main 676ad9c, 2026-10-09)

- `README.md:167-182` "升级运行时": close every session using the mailbox, then `upgrade --confirm`; rollback and
  recover bullets. Nothing about how to stop the bridges or what to restart afterwards.
- `plugins/agent-relay/skills/collaboration-ops/SKILL.md:66-80`: the upgrade runs only after the user agrees and has
  closed every session using the mailbox; nothing about `pkill` or restarting ChatGPT.
- CHANGELOG upgrade sections per version tell users to close sessions and check
  `pgrep -fl "agent-relay/runtime/dist/server.js"`.

## Assumptions (accepted by the user 2026-10-09)

1. Two ways to stop the bridges are documented: quitting the apps (Claude Code sessions, the ChatGPT app), then
   reopening them after the upgrade; or ending the bridge processes with `pkill`, after which the Claude Code sessions
   are reopened and the ChatGPT app must be quit completely (⌘Q) and reopened, because open Codex threads otherwise
   keep "Transport closed".
2. The documented `pkill` is `pkill -TERM -f "[a]gent-relay/runtime/dist/server.js"` (the bracket keeps it from
   matching the shell that runs it); the check stays `pgrep -fl "agent-relay/runtime/dist/server.js"`.
3. The skill says an agent never runs `pkill` without the user's explicit consent for that step (stopping the
   bridges ends every mailbox connection, its own included).
4. Docs only: README "升级运行时", collaboration-ops skill upgrade paragraph, CHANGELOG `[Unreleased]`. No code,
   interface or bridge change; no release in this module (the next release's upgrade steps will carry it).
5. Validate on one Python (docs only; `test_packaging` and doc checks run in it); the round-2 coordinator reviews; the
   user merges after every CI check has finished green.

## Decisions

- **D132 README.** "升级运行时" gains a short "停 bridge 的两种方式" paragraph per assumptions 1–2.
- **D133 skill.** collaboration-ops upgrade paragraph: how the bridges may be stopped (assumptions 1–3), and after a
  `pkill` remind the user to quit and reopen ChatGPT and reopen Claude Code sessions.
- **D134 CHANGELOG** `[Unreleased]`.

## Requirements

0. README and the skill name both ways, the ChatGPT restart after `pkill`, the bracketed `pkill`, and (skill) the
   consent rule.
1. Validate passes; CI green (all checks finished).

## Boundaries

- Never: run `pkill` on the real host as part of this module; change code.

## Success criteria

Someone upgrading the runtime by `pkill` is told to restart ChatGPT, and the documented `pkill` does not kill its own
shell.

## Open questions

None. Assumptions 1–5 and D132–D134 accepted on 2026-10-09 ("接受").
