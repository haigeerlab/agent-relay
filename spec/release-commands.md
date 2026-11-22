# Spec: release-commands

<!-- spec-guard: review approved fe0edff9d2ec -->

## Objective

Turn agent-relay's release steps, today spread over `RELEASING.md`, the README "更新与升级" section and session memory,
into one maintainer command, `scripts/release.py`, called step by step. The owner session calls it when releasing; the
autopilot "插件" template calls it for its release steps. Ledger item 4ZW316D.

Request (ecosystem-lead #21887, relaying autopr-design #21882; S101 r3, approved by the user on 2026-11-21 "按推荐批准"):
"请把 agent-relay 的发版步骤整理成可调用的命令，给 autopilot 的「插件」模板调用。现在这些步骤多半散在说明里。" Follow-up
(ecosystem-lead #22135, 2026-11-22): align with Spec Guard's `scripts/release.py` (subcommands check / prepare / publish /
install / smoke / evidence, the last output line is JSON). The template's steps are the "1. 插件" table of the ecosystem
ledger `research/2026-11-21-合并之后的接管梳理.md` (report impact, full tests → merge → tag → Release, check the tag, install
on both hosts — for agent-relay also stop the bridge and `upgrade --confirm` — check the install, take effect, verify
with doctor / smoke, close out). agent-relay is one of the four plugins the pipeline itself uses, so its release goes at
most to **prepare** ("备好等批") without the user.

Readers: the user (approves, authorises each write step); the owner session (runs the command, dispatches the Plan's
tasks to Codex and accepts them); the autopilot template (calls the read-only steps).

## What exists today (main 37566cf, v0.9.6, interface 2.11)

- `RELEASING.md`: prose steps — before release, the release PR (both `plugin.json`, bridge version, CHANGELOG, both
  READMEs), `git tag -a` + `git push` + `gh release create`, after release (update both hosts, `upgrade --confirm` when
  bridge runtime files changed, doctor, acceptance).
- `plugins/agent-relay/hooks/native_collaboration_runtime.py`: `status`, `upgrade --confirm`, `rollback --confirm`,
  `recover --confirm`, `doctor`. `upgrade` refuses while a bridge server of the runtime runs (`_servers_running`, a `ps`
  listing); nothing in the repo stops the bridge — the README tells the user to close sessions / ⌘Q ChatGPT, or to
  `pkill` it themselves. `RUNTIME_FILES` decides whether a change needs a runtime upgrade (runtime-mark-scope).
- `scripts/acceptance/preflight.py`: read-only; finds the copy each host runs and hashes it (`tree_hash`, `IGNORED`).
- `scripts/validate.sh` runs every `plugins/agent-relay/hooks/test_*.py`, sealed in a throwaway HOME; `test_ci_scope.py`
  already tests a file under `scripts/` this way.
- Spec Guard's `scripts/release.py` (its module `release-command`): schema
  `spec-guard.release/v1`, statuses ok / preview / refused / waiting-on-user / failed → exit 0 / 0 / 2 / 3 / 1, a per-version
  local record, `--confirm` for publish and install.

## Assumptions (confirmed by the user, 2026-11-22: "按推荐确认")

1. **Form**: maintainer script `scripts/release.py`, for releasing agent-relay itself only; not shipped as a plugin
   command. Python standard library plus the `git`, `gh`, `claude`, `codex`, `ps` already on the machine; every command
   run as an argument list, never through a shell.
2. **Subcommands**: Spec Guard's six — `check`, `prepare`, `publish`, `install`, `smoke`, `evidence` — plus `upgrade`
   (runtime upgrade; only agent-relay has a runtime). See D276.
3. **Output and exit codes** as Spec Guard: human-readable Chinese lines, then one JSON line last on stdout
   (D278).
4. **Local record**: each step's facts go to `<state home>/release/<version>.json` (`state_home()`, default
   `~/.agent-relay/release/`); later steps read it. Never in the repo.
5. **Steps** (D279–D285).
6. **Authorisation ceiling is prepare**: autopilot may call `check`, `prepare`, and the read-only `smoke` and `evidence`
   without the user. `publish`, `install`, `upgrade` only preview without `--confirm` and touch neither the remote nor
   the hosts; `--confirm` is passed on the user's own words, which is the caller's responsibility. The command does not
   judge where an authorisation came from (as Spec Guard).
7. **Not this command's**: drafting or merging the release PR (versions, CHANGELOG, README); ⌘Q-reopening ChatGPT,
   `/clear` in open sessions; telling ecosystem-lead or consumers; real-host acceptance; the ecosystem ledger.
8. **Tests**: `plugins/agent-relay/hooks/test_release_command.py`, found by `validate.sh`'s glob (same pattern as
   `test_ci_scope.py`). Temporary git repos with a bare remote, fake `gh` / `claude` / `codex` / `ps` / `node` on
   `PATH`, fake HOME / `AGENT_RELAY_HOME` / `CLAUDE_CONFIG_DIR` / `CODEX_HOME`; no network, no real host.
9. **Docs**: `RELEASING.md`'s "发版" and "发版后" sections call the subcommands, keeping the reasons. No plugin
   behaviour, interface or version change; the change is `scripts/`, one new test and `RELEASING.md`, so it needs no
   release of its own.
10. **Privacy**: local paths appear only in output and the local record, never in repo files
    (`scripts/check_local_paths.py` stays green).
11. **Language**: Spec and Plan in English as recent modules; the capability-map row in Chinese.
12. **Plan granularity**: about eight tasks, each with its test file, the assertions and an acceptance command, written so
    an executor who has not seen this conversation (Codex via `/delegate:run`) can do it.

## Decisions

- **D276 `upgrade` is its own subcommand.** Only a release that changes `RUNTIME_FILES` needs it, and it is the one step
  that needs the user to close every session using the mailbox. Kept apart, `install` can finish without interrupting
  anyone, and `upgrade` can wait for the user.
- **D277 `prepare` does not rerun the tests.** The full test run is CI's four combinations on the merge commit, which
  `check` verifies; CI runs the same entry, `scripts/validate.sh`. No `--run-tests` flag now.
- **D278 Output.** Every subcommand's last stdout line is
  `{"schema": "agent-relay.release/v1", "step": <subcommand>, "version": <version or null>, "status": <status>, ...facts}`;
  `status` is `ok`, `preview`, `refused`, `waiting-on-user` or `failed`, exit code 0, 0, 2, 3, 1. A refusal carries
  `reason` (a stable kebab-case code) and the Chinese lines say which check failed. Any unexpected exception is `failed`
  with the message, still as a JSON last line. Argument errors exit 2 with `status: refused`, `reason: usage`.
  Common options: `--repo` (default: this checkout), `--remote` (default `origin`), `--github owner/repo` (default: parsed
  from the remote URL). `--version` where the step needs it (`check` derives it from the merge commit).
- **D279 `check --pr <n>` (read only).** Refused with its own reason when any fails: the PR is not merged (`gh api
  repos/<repo>/pulls/<n>`, `merged`); `git fetch` then `<remote>/main` ≠ the merge commit (`main-moved`); the CI runs on the
  merge commit are empty, unfinished or not all `success` (`ci-not-green`); the two `plugin.json` versions differ or are
  invalid (`version-mismatch`); `README.md` / `README.en.md` lack `--ref v<version>` or their status line does not name the
  version (`readme-mismatch`); `CHANGELOG.md` has no `## [<version>]` section (`changelog-missing`); the bridge version
  (`bridge/package.json`) is higher than the plugin version (`bridge-version`); tag `v<version>` exists locally or on the
  remote (`tag-exists`). On `ok` the JSON carries the impact facts: `mergeCommit`, `previousTag` (the highest `v*` tag
  that is an ancestor), `interface` `{from, to}` (from `plugins/agent-relay/interface.json` at both commits),
  `runtimeUpgrade` (whether any bridge file under `RUNTIME_FILES` differs between the two commits) and `runtimeFiles` (the
  list). Writes only the local record.
- **D280 `prepare --version <v>` (local only).** Needs a recorded `check` ok for this version. `git archive` of the merge
  commit, limited to `.claude-plugin` and `plugins/agent-relay`, extracted into a fresh `mktemp -d` directory with a fixed
  prefix; writes there `MANIFEST.json` (relative path → sha256 for every file of `plugins/agent-relay`, minus
  `preflight.py`'s `IGNORED` names) and `release-notes.md` (the CHANGELOG section of the version, without its heading).
  Records `dir`, the manifest's sha256 and the file count. No remote write, no host change.
- **D281 `publish --version <v> [--confirm]`.** Needs recorded `check` and `prepare` ok, and `<remote>/main` still at the
  merge commit. Without `--confirm`: `preview`, listing the three commands it would run. With it: `git tag -a v<v>
  <merge commit> -m "agent-relay <v>"`, `git push <remote> v<v>`, `gh release create v<v> --verify-tag --title "agent-relay
  <v> (interface <to>)" --notes-file <release-notes.md>`; then `git ls-remote <remote> refs/tags/v<v>^{}` must name the
  merge commit, else `failed`. Records the tag, the Release URL and the peeled commit.
- **D282 `install --version <v> [--confirm]`.** Needs recorded `publish` ok. Reads how each host gets agent-relay:
  - Claude: `known_marketplaces.json` under `CLAUDE_CONFIG_DIR` (default `~/.claude`) for `agent-relay-marketplace`.
    Source `directory` (a local clone): refused (`clone-not-clean`) when the clone has uncommitted changes, is not on
    `main`, or cannot fast-forward; else `git -C <clone> pull --ff-only` and its HEAD must equal the tag's commit
    (`clone-not-at-tag` otherwise). Then, for either source, `claude plugin marketplace update agent-relay-marketplace` and
    `claude plugin update --scope user agent-relay@agent-relay-marketplace`.
  - Codex: `config.toml` under `CODEX_HOME` (default `~/.codex`) is first copied into the local record's directory
    (`<version>-config.toml.bak`). When `[marketplaces.agent-relay-marketplace]` has a `ref` line, exactly that one line is
    replaced by `ref = "v<v>"` and every other byte kept; a missing section, or zero or several `ref` lines in a section
    whose source is a git URL, is refused (`codex-ref-ambiguous`) with the file unchanged. A local-path source has no
    `ref` and is left as is. Then `codex plugin add agent-relay@agent-relay-marketplace`.
  - Verification: the copy each host now runs (found as `preflight.py` finds it) is compared file by file with
    `MANIFEST.json`; any missing, extra or different file is `failed` and listed.
  Without `--confirm`: `preview` with the detected sources and the exact commands; nothing runs, no file changes. Records
  both hosts' copy paths, versions and the time.
- **D283 `upgrade --version <v> [--confirm]` — the local destructive step.**
  - `check` recorded `runtimeUpgrade: false` → `ok` with `skipped: true` and nothing done.
  - Needs recorded `install` ok (README: update the plugin before the runtime).
  - Never stops the bridge: no `kill` / `pkill`, no quitting any application, no closing sessions.
  - Counts running bridge servers of the runtime as `_servers_running` does. Without `--confirm`: `preview` with that
    count and the command it would run. With `--confirm` and a count above zero: `waiting-on-user`, saying the user must
    close every session using the mailbox (Claude Code sessions, and ⌘Q ChatGPT), and that nothing was changed.
  - With `--confirm` and nothing running: runs the **installed** copy's `native_collaboration_runtime.py upgrade
    --confirm` (the Claude copy found by `install`), parses its JSON. `upgraded` or `current` → `ok` with `previous`,
    `backup`; anything else → `failed`, printing the `rollback --confirm` and `recover --confirm` commands for the user.
    It never rolls back or recovers by itself.
- **D284 `smoke --version <v>` (read only).** Runs the installed copy's `native_collaboration_runtime.py doctor` and
  `status`. Doctor `fail` → `failed`; `bridge.current` false while `runtimeUpgrade` was true → `waiting-on-user`
  (upgrade not done); a `claude-plugin` check that is not `ok`, or `codex-restart` `warn` (ChatGPT not reopened) →
  `waiting-on-user` naming the user's action; else `ok`. The JSON lists every doctor check's name and state.
- **D285 `evidence --version <v> [--output <file>]` (writes no repo file).** Renders the local record as a short Markdown
  summary (merge commit, tag, Release URL, impact facts, both host copies, upgrade, smoke result, what is still waiting on
  the user) to stdout, or to `--output`, which must not be inside the repo (`output-in-repo`). `ok` even when earlier
  steps are missing; it says which.
- **D286 Order and re-runs.** Every step re-reads the record; a step whose prerequisite is not recorded ok is
  `refused` (`needs-<step>`). Re-running a finished step is allowed: `check`, `prepare`, `smoke`, `evidence` redo their
  work; `publish` with the tag already on the remote at the merge commit and a Release present is `ok` without writing;
  `install` and `upgrade` redo their checks and only run commands whose effect is missing. The record is written
  atomically (temp file + rename), one step replaced at a time.

## Requirements

1. `scripts/release.py` implements D276–D286, standard library only, no shell strings.
2. `plugins/agent-relay/hooks/test_release_command.py` covers the acceptance criteria below with fakes only; it runs under
   `bash scripts/validate.sh`.
3. `RELEASING.md` "发版" and "发版后" call the subcommands and say who does what: the user's authorisation before
   `publish` / `install` / `upgrade --confirm`, closing sessions, ⌘Q ChatGPT, acceptance.

## Acceptance criteria

- **AC1** `check`: all good → `ok` with the impact facts; each failure in D279 → `refused` with its `reason`; on
  `runtimeUpgrade` a change only under `bridge/test/` is false and one under `bridge/src/` is true.
- **AC2** `prepare`: the extracted tree holds only `.claude-plugin` and `plugins/agent-relay`; `MANIFEST.json` matches
  the merge commit's files; `release-notes.md` equals the CHANGELOG section; the fakes record no `gh` or `git push` call.
- **AC3** `publish`, `install`, `upgrade` without `--confirm`: the fakes record no write command (no `git tag`, `git
  push`, `gh release create`, `claude plugin`, `codex plugin`, runtime `upgrade`), `config.toml` and the clone are
  byte-identical. With `--confirm`: the calls happen in the D281 / D282 / D283 order; a tag peeling to another commit is
  `failed`.
- **AC4** Codex config: only the `ref` line changes, a backup exists before the change; a missing section or ambiguous
  `ref` → `refused` with the file unchanged.
- **AC5** Install verification: a host copy with one changed, missing or extra file → `failed` naming it; matching
  copies → `ok`. A dirty or non-`main` clone → `refused`, the clone unchanged.
- **AC6** `upgrade`: `runtimeUpgrade` false → skipped; a running bridge (fake `ps`) with `--confirm` →
  `waiting-on-user`, exit 3, the runtime script not called; nothing running → it is called with `upgrade --confirm`; its
  error → `failed` with the rollback and recover commands printed and neither run. No test sees a `kill` call.
- **AC7** `smoke`: doctor fail → `failed`; `codex-restart` warn → `waiting-on-user`; all ok → `ok`.
- **AC8** `evidence`: prints the summary; `--output` inside the repo → `refused`.
- **AC9** Every subcommand's last stdout line parses as JSON with the D278 fields and the exit code matches `status`;
  `bash scripts/validate.sh` and `python3 scripts/check_local_paths.py` pass.

## Boundaries

- **Will do**: Requirements 1–3 and their regressions.
- **Ask first**: letting `publish`, `install` or `upgrade` act without `--confirm`; changing anything in `config.toml`
  beyond the `ref` line; making the command judge the user's authorisation; any bridge stop or automatic rollback.
- **Won't do**: Assumption 7; any plugin behaviour, interface or version change; changes to `.github/` or
  `scripts/ci_scope.py`.

## Open questions

None.
