# Plan: release-commands

<!-- spec-guard: review approved -->

Based on [`spec/release-commands.md`](../../spec/release-commands.md) (approved by the user on 2026-11-22: assumptions
1–12, D276–D286, AC1–AC9). Each task below is implemented by Codex (`/delegate:run`, write) dispatched by the owner
session, and accepted by the owner (baseline HEAD, `git status` / `git diff`, the acceptance command; no self-report is
trusted). Nothing here touches the main clone, the hosts, the runtime or the mailbox on this Mac: every test uses fakes.

## For the executor (read first)

- Read `spec/release-commands.md` in full; the Decisions (D276–D286) are the contract. Do not change the plugin under
  `plugins/agent-relay/` except adding the one test file; do not touch `.github/`, `scripts/ci_scope.py`,
  `scripts/validate.sh`, versions, CHANGELOG or the READMEs.
- Files of this module: `scripts/release.py` (new), `plugins/agent-relay/hooks/test_release_command.py` (new),
  `RELEASING.md` (Task 9 only), `tasks/release-commands/todo.md` (tick your task).
- Python standard library only; every subprocess as an argument list (`subprocess.run([...])`, never `shell=True`).
  Code and comments in English; human-readable output lines in Chinese, as Spec Guard's `scripts/release.py`.
- Reuse, don't copy: `state_home()` and `RUNTIME_FILES` from `plugins/agent-relay/hooks/native_collaboration_runtime.py`;
  `IGNORED`, `tree_hash` and the host-copy discovery (`claude_install`, `codex_install`, `_directory_plugin`) from
  `scripts/acceptance/preflight.py` (import by path as `test_ci_scope.py` imports `scripts/ci_scope.py`). If a function
  there needs a parameter (e.g. a config dir) to be testable, add it with the current behaviour as default and keep
  `preflight.py`'s output unchanged.
- No local absolute path or account name in any committed file (`python3 scripts/check_local_paths.py`).
- Test first: write the task's tests, see them fail, then implement. Each task ends green on its acceptance command and
  on `bash scripts/validate.sh` (run `npm ci` in `plugins/agent-relay/bridge` once beforehand if `node_modules` is
  missing; without it the bridge part is reported as skipped, which is acceptable for these tasks).
- Commit message in Chinese with the `feat:`/`test:`/`docs:` prefix and `（release-commands Task N）`.

## Architecture decisions

- One file, one `main(argv)`; each subcommand a function returning a facts dict; `main` prints the JSON last line and
  maps `status` to the exit code (D278). A `ReleaseError(message, status, reason)` carries refusals and failures.
- A small `run(args, timeout)` wrapper is the only place that starts processes, so tests observe every call through fakes
  on `PATH` that append their argv to a log file.
- The local record is `state_home() / "release" / "<version>.json"`, written atomically, one step's facts replaced at a
  time (D286). `--state-home` is not added: tests set `AGENT_RELAY_HOME`.
- Host paths come from `CLAUDE_CONFIG_DIR` (default `~/.claude`) and `CODEX_HOME` (default `~/.codex`), as the rest of the
  plugin; tests point them at temp dirs.

## Task List

### Task 1: skeleton, output contract and test fixture (D278, D286 record; AC9)
`scripts/release.py`: argparse with the seven subcommands and the common options (`--repo`, `--remote`, `--github`;
`--pr` for `check`; `--version` for the others; `--confirm` for `publish`/`install`/`upgrade`; `--output` for
`evidence`). Every subcommand body raises `ReleaseError("not implemented yet", "refused", "not-implemented")` for now.
`main` always prints Chinese lines then one JSON line `{"schema": "agent-relay.release/v1", "step", "version", "status",
...}`; argparse errors become `refused` / `reason: usage` / exit 2 (override `ArgumentParser.error`); any other exception
becomes `failed` with `error`. Record helpers `read_record(version)` / `write_record(record, step, facts)` (temp file +
`os.replace`), version validated by `^[0-9]+\.[0-9]+\.[0-9]+$` (`invalid-version` otherwise).
`test_release_command.py`: a `Fixture` used by every later task — temp dir with a work repo and a bare remote
(`origin`), a minimal agent-relay tree committed (both `plugin.json`, `interface.json`, `bridge/package.json`,
`bridge/src/x.ts`, `bridge/test/x.test.ts`, READMEs with status line and `--ref`, CHANGELOG), fake `gh`/`claude`/`codex`/
`ps`/`node` scripts on `PATH` that log argv to `calls.log` and answer from JSON files the test writes, `HOME`,
`AGENT_RELAY_HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` in the temp dir; `run_release(*args)` returns
`(exit_code, json_last_line, stdout)`.
Tests: unknown subcommand and a missing `--version` → exit 2, `refused`, `usage`; `--version 1.2` → `invalid-version`;
a forced exception (monkeypatched subcommand) → exit 1, `failed`; the record writer keeps other steps' facts and leaves
no temp file.
**Accept**: `python3 -B plugins/agent-relay/hooks/test_release_command.py` passes; `bash scripts/validate.sh` passes.

### Task 2: `check --pr` (D279; AC1)
Implement as D279. `gh api repos/<repo>/pulls/<n>` and `gh run list --repo <repo> --commit <sha> --json
conclusion,status,workflowName` (fake answers); `git fetch <remote>`; files read with `git show <sha>:<path>`;
`previousTag` = highest `v*` tag (`git tag --merged <sha> --sort=-v:refname`); `runtimeUpgrade` = any path from
`git diff --name-only <previousTag> <sha> -- plugins/agent-relay/bridge/` whose bridge-relative name matches
`RUNTIME_FILES` (prefix match for entries ending in `/`, exact otherwise). No previous tag → `runtimeUpgrade: true`,
`previousTag: null`. Records `check` with the facts and the version.
Tests, one per reason: `not-merged`, `main-moved`, `ci-not-green` (empty list, one `in_progress`, one `failure`),
`version-mismatch`, `readme-mismatch` (zh and en separately), `changelog-missing`, `bridge-version`, `tag-exists` (local
tag; remote-only tag); `ok` case asserts every fact; `runtimeUpgrade` false for a change only in `bridge/test/`, true
for `bridge/src/`; `calls.log` holds no `git push`, `git tag` (creating), `gh release`.
**Accept**: as Task 1.

### Task 3: `prepare` (D280; AC2)
Needs `check` ok in the record (`needs-check`). `git archive --format=tar <sha> .claude-plugin plugins/agent-relay`,
extracted with `tarfile` (refuse members with absolute paths or `..`) into `tempfile.mkdtemp(prefix="agent-relay-release-")`;
writes `MANIFEST.json` (sorted `{relative path under plugins/agent-relay: sha256}`, skipping `preflight.IGNORED` names) and
`release-notes.md` (the body of `## [<version>]` up to the next `## [`). Records `dir`, `manifestSha256`, `files`.
Re-run makes a fresh dir.
Tests: tree holds exactly `.claude-plugin` and `plugins/agent-relay` plus the two files; manifest equals hashes computed
from `git show`; notes equal the section; `needs-check` without a check; no remote write in `calls.log`.
**Accept**: as Task 1.

### Task 4: `publish` (D281; AC3 for publish)
Needs `check` and `prepare` ok, `<remote>/main` still the merge commit (`main-moved`). Without `--confirm`: `preview`,
facts list the three commands. With it: `git tag -a`, `git push <remote> v<v>`, `gh release create ... --verify-tag
--notes-file`, then `git ls-remote <remote> refs/tags/v<v>^{}` must equal the merge commit (`failed`, reason
`tag-mismatch`, otherwise). Re-run (D286): tag already on the remote at the merge commit and `gh release view v<v>`
succeeds → `ok`, `alreadyPublished: true`, no write; tag on the remote at another commit → `refused` `tag-mismatch`.
Tests: preview logs no write and the bare remote has no tag; confirm creates the annotated tag on the bare remote at the
merge commit and logs `gh release create` with `--verify-tag`; re-run case; tag-mismatch case (tag pushed by the test at
another commit).
**Accept**: as Task 1.

### Task 5: `install` — host detection and the Codex config edit (D282 first half; AC4)
Pure functions first, then wired into `install` preview: `claude_source()` reads `known_marketplaces.json` for
`agent-relay-marketplace` → `{"kind": "directory", "path": ...}` or `{"kind": "git", ...}`; `codex_ref_change(text,
version)` returns the new text with exactly the `ref` line of `[marketplaces.agent-relay-marketplace]` replaced
(`ref = "v<version>"`, keeping the line's indentation and newline), `None` when the section's source is a local path,
and raises `refused`/`codex-ref-ambiguous` when the section is missing or a git source has zero or several `ref` lines.
`install` without `--confirm` → `preview` with both sources and the exact commands, no file changed.
Tests: byte-for-byte only the ref line changes (other sections, comments, CRLF-free trailing newline kept); missing
section, two `ref` lines, git source without `ref` → refused, file unchanged; local-path source → no change; preview
leaves `config.toml` and `known_marketplaces.json` byte-identical and logs no `claude plugin`/`codex plugin` call.
**Accept**: as Task 1.

### Task 6: `install --confirm` — run and verify (D282 second half; AC3 for install, AC5)
Needs `publish` ok (`needs-publish`). Order: (1) Claude directory source: refuse `clone-not-clean` when
`git status --porcelain` is non-empty, the branch is not `main`, or `git merge-base --is-ancestor HEAD <tag>` fails;
`git pull --ff-only`; HEAD must equal the tag's commit (`clone-not-at-tag`). (2) `claude plugin marketplace update
agent-relay-marketplace`; `claude plugin update --scope user agent-relay@agent-relay-marketplace`. (3) back up
`config.toml` to `<state home>/release/<v>-config.toml.bak`, write the Task 5 change if any; `codex plugin add
agent-relay@agent-relay-marketplace`. (4) find each host's copy as `preflight.py` does and compare with `MANIFEST.json`;
any missing / extra / different file → `failed` with the list. Records both copies' paths and versions and the time.
Re-run: steps whose effect is already there (clone at tag, ref already `v<v>`) are skipped, the verification always runs.
Tests: dirty clone, clone on another branch, clone ahead of the tag → refused, clone unchanged; happy path calls in the
listed order and backup exists before the config changes; a fake host copy with one changed / missing / extra file →
`failed` naming it; matching copies → `ok`.
**Accept**: as Task 1.

### Task 7: `upgrade` (D283; AC6)
`check` recorded `runtimeUpgrade: false` → `ok`, `skipped: true`, no call. Else needs `install` ok. Count bridge servers
as `native_collaboration_runtime._servers_running(default_root())` (import it; the fake `ps` answers). Without
`--confirm`: `preview` with the count and the command. With `--confirm`: count > 0 → `waiting-on-user` (exit 3), message
says close every session using the mailbox and ⌘Q ChatGPT, nothing called; count 0 → run
`python3 -B <installed Claude copy>/hooks/native_collaboration_runtime.py upgrade --confirm`, parse its last JSON line:
`upgraded`/`current` → `ok` with `previous`, `backup`; anything else or a non-JSON output → `failed`, printing the
`rollback --confirm` and `recover --confirm` commands (not run). Add a test-only guard: the module never references
`kill`/`pkill` (a test greps `scripts/release.py` for `kill(` and `"pkill"`).
Tests: skipped case; running bridge + confirm → exit 3 and the runtime script not called (the installed copy in the
fixture is a fake script that logs its argv); confirm with nothing running → called once with `upgrade --confirm`;
fake script answering `{"state": "error"}` → `failed`, output names both commands, neither called; no `kill` in the file.
**Accept**: as Task 1.

### Task 8: `smoke` and `evidence` (D284, D285; AC7, AC8)
`smoke`: run the installed copy's `native_collaboration_runtime.py doctor` and `status` (fake scripts in tests), map as
D284, facts list every check `{name, state}`. `evidence`: Markdown summary of the record (sections: release, impact,
hosts, runtime upgrade, smoke, waiting on the user; missing steps named) to stdout or `--output`; an `--output` resolving
inside `--repo` → `refused` `output-in-repo`. Both read-only for hosts and repo.
Tests: doctor fail → `failed`; `codex-restart` warn → `waiting-on-user` (exit 3); `claude-plugin` warn →
`waiting-on-user`; `bridge.current` false with `runtimeUpgrade` true → `waiting-on-user`; all ok → `ok`; evidence with
only `check` recorded names the missing steps; `--output` in the repo refused, outside written.
**Accept**: as Task 1.

### Task 9: `RELEASING.md` (Requirement 3)
Rewrite "发版" and "发版后" to call `python3 scripts/release.py <step>` in order, saying per step what it checks or does,
which steps autopilot may run alone (`check`, `prepare`, `smoke`, `evidence`), which need the user's words before
`--confirm` (`publish`, `install`, `upgrade`), and the user's own actions (close sessions before `upgrade`, ⌘Q ChatGPT,
new sessions, acceptance). Keep "版本号", "发版前", "发版 PR", "撤回一次合并" and the reasons; the manual `git tag` /
`gh release create` block moves under a short "命令不可用时" fallback. Add one line on the JSON last line and exit codes.
**Accept**: `python3 scripts/check_local_paths.py` passes; `bash scripts/validate.sh` passes; the owner reads the diff.

## Checkpoints

- After each task (report): owner accepts the task (diff, acceptance command, `validate.sh`) and ticks it in `todo.md`.
- After Task 8 (report): a read-only dry run on this Mac by the owner — `python3 scripts/release.py check --pr <the
  v0.9.6 release PR>` against the real remote. Expected: `refused` with `tag-exists` (the last check in D279), which shows
  every earlier check passed on a real release; any other reason is a defect to fix before the PR.
- Final (gate): PR review and merge by the user.

## Risks

- Host files' exact shapes (`known_marketplaces.json`, Codex `config.toml` marketplace section, `codex plugin list
  --json`) are taken from `preflight.py` and the doctor's tests, not re-measured; a mismatch on the real host shows up as
  `refused` / `failed`, never as a silent write.
- `upgrade` imports private `_servers_running`; renaming it breaks the command — Task 7's test pins the import.
- Running `install --confirm` for real changes the user's clone and both hosts; it is never run by this module's tests or
  checkpoints.

## Open questions

None.
