# Acceptance record: round2-rerun (2026-10-07)

Targeted rerun after `round2-fixes` (PR #12, main fc7ee7e) of the round-2 rows that failed or were partial, judged
against the hardening-target column and the round2-fixes acceptance (D49–D52). See
[2026-10-07-round2.md](2026-10-07-round2.md) for the full run and findings R2-1..R2-10.

## Run

| Field | Value |
|---|---|
| agent-relay commit | fc7ee7e (main checkout fast-forwarded; Codex plugin cache re-copied with `codex plugin add`, 0 diffs; Claude loads the plugin in place from the checkout) |
| Spec Guard | 0.51.2 on both hosts |
| Claude Code / Codex | 2.1.291 / codex-cli 0.160.0, app-managed 0.160.1, ChatGPT.app 26.930.61225 |
| Shell environment | PATH resolves nvm v12.22.12 first; `python3` = `/usr/bin/python3` 3.9.6 unless a row says otherwise |
| Codex `approvals_reviewer` and App selector | `guardian_subagent` (App 帮我批准) → `user` set by the user's terminal script (backup `config.toml.bak-rerun`), App selector left at 帮我批准 (R2-2: independent of the file) → restore in E3 |
| Sessions | S7 background Claude `ar-acc-rerun-sg-origin` (spec-guard worktree, allowed only the mailbox tools, the controller at the main-checkout path, `printf`, `date`, read-only `git -C design-test`); new Codex App thread in design-test registered `ar-acc-rerun-design-codex` (guide, user-authorized computer use) |
| Permission changes | `approvals_reviewer = "user"`; ten bridge allow rules in design-test and in the new worktree `design-test-rerun-wt` (branch `ar-acc-rerun-wt`), by the user's terminal script; revert in E3 |

## Results

| Id | Steps taken | Result | Evidence |
|---|---|---|---|
| R2-1 / A1 | `doctor` with `/usr/bin/python3` and v12 first in PATH | pass | `probe ok: the bridge starts with node …/v24.18.0/bin/node (v24.18.0, from claude-entry) and lists 17 tools`; only warnings: codex-approval (guardian, expected before the switch) and a stale wake binding of a round-2 test identity |
| R2-9 / D7 | `state_migration.py detect` with `/usr/bin/python3` 3.9.6 | pass | `verdict: blocked` (target already populated, never merged; old delegation 27f0de `creating`), old mailbox counts 62/83/83/60 as in round 1 |
| R2-7 / C1–C6 Claude → Codex | S7, default PATH (v12 first), controller at the main-checkout path, **no `--node`**: create `r3-cx-review`, continue ×2 (gutter, write request), second create with the same name, ambiguous status, status and cancel by short id | pass | create `completed`, `transport=agent-relay-bridge`, `resultDelivery=enqueued`, #139 `#3a5bd9`; continue #140 `72px`; write request refused #141 ("filesystem permissions prohibit writes … design/notes.txt does not exist"), `git status --short` empty; second create #142 `OK` from a different identity; `status --name` → `session-name-ambiguous` candidates `4aaf78`, `21cac4`; each `status --disambiguator` `completed`/`notLoaded`; both cancels `cancelled`; all results acked |
| R2-6 / D49 / C3 Codex → Claude | new design-test Codex thread, controller without `--node`: per target create + 3 continues, `status` immediately after every resume, `bridge_wait` per round | pass | plain repository `r3-cc-plain`: #143 (create, `created`/`idle`), #144, #145, #146 (continues, each `running`, status right after resume `busy/running`, no prerequisite); worktree `r3-cc-wt`: #147–#150 likewise; 8/8 results returned and acked; no `idle/working`, no `target-busy`, no `registration-missing`; both sessions `cancelled`. Replies carry `OK-N` plus the envelope's reviewer note (by design). The origin's first controller call inside the Codex sandbox failed on a read-only control database and was rerun outside the sandbox with approval (sandbox behaviour) |
| R2-10 / D52 (open session) | all ten bridges stopped (SIGTERM), this guide session left open, `uninstall-claude --confirm-uninstall` from it | pass | "Native Claude MCP entry removed; deny rules kept: 4 Claude Code session(s) still open … close every Claude Code session first, then run this in a terminal:" + the exact command; 7 `mcp__agent-relay` deny rules still in `settings.json`; no worker tool appeared in the open session |
| R2-9 reinstall | `uninstall-codex`, `native_collaboration_runtime.py uninstall --confirm`, then `install --node <v24> --npm <v24 npm>` with `/usr/bin/python3` | pass for Python 3.9 (with R2-12) | uninstall `{"state": "uninstalled"}`, `mailbox/` and `data/` kept; first install `native bridge install failed at …/v24.18.0/bin/npm` (R2-12, nothing replaced); with v24 first in PATH and still `/usr/bin/python3`: `ready` around the kept history (round 2 crashed here); `install-codex` re-attached |
| R2-10 / D52 (second refusal) | The user ran the guide's final script with `!` from this guide session, so four Claude Code sessions were still open (`~/.claude/sessions/` 18503, 22035, 23068, 28724) | pass (refusal path) | "Native Claude MCP entry absent; deny rules kept: 4 Claude Code session(s) still open …" plus the terminal command; deny rules 7 before and after; `install-claude` then re-attached the entry (7 rules) |
| R2-10 / D52 (refusal, 3rd and 4th) | the guide's `r210_terminal.sh` run twice with `!` from inside this guide session (so not with every session closed) | pass (refusal path) | 23:57: 4 live sessions → rules kept (7 → 7), command printed; 00:02: 4 live sessions and 4 bridges → "deny rules kept: 4 Claude Code session(s) still open; 4 agent-relay bridge server(s) still running …" (7 → 7); `install-claude` re-attached each time |
| R2-10 / D52 (all sessions closed) | removal once no Claude Code session is alive | not run on the real host | A `!` command always runs inside an open session, so the positive path needs the desktop app quit and Terminal.app; the user chose to rely on the module's Task 7 check 3 (temporary HOME, real process: rules removed after the session process exited) |

## Findings

R2-11. **Claude's install records point at a stale cache copy** (host behaviour; skills/README). Every
`installed_plugins.json` entry for agent-relay has `installPath ~/.claude/plugins/cache/agent-relay-marketplace/agent-relay/0.1.0`,
last copied at ef77d7f, while Claude says the plugin "loads in place" from the checkout; `claude plugin update` and a
re-install do not refresh it (version unchanged). An agent resolving `$ROOT` from the install record runs old hooks:
round-2 S6b ran its controller from that cache. The skills should resolve the root from the running plugin
(`CLAUDE_PLUGIN_ROOT`) and never from the install record.

R2-12. **`node` from PATH is still used outside the D50 order** (product, follow-up to R2-7). `install --npm <npm>`
runs npm through its `#!/usr/bin/env node` shebang, so with v12 first in PATH the bridge build fails
(`native bridge install failed at …/npm`); `native_collaboration_retire.py --node` defaults to `shutil.which("node")`
and refuses ("pinned retire command did not retire …") in the same shell. The acceptance kit's `cleanup.sh` also
fails under `/usr/bin/python3` 3.9 ("cannot read …/bridge.sqlite: unable to open database file", the R2-9 pattern).
Expected: run npm with the chosen node's directory first in PATH, use the D50 order in retire, and apply the D51
snapshot reader in `cleanup.sh`.

## Cleanup

| Id | Result |
|---|---|
| E1 | S7 stopped; delegated sessions stopped by their cancels; envelopes `r3-cx-review` ×2, `r3-cc-plain`, `r3-cc-wt` `cancelled` |
| E2 | `ar-acc-rerun-design-codex`, `ar-acc-rerun-sg-origin` retired by `cleanup.sh rerun --confirm`; delegated `r3-cx-review-01a11705`, `r3-cx-review-01a11706`, `r3-cc-plain-a1298c9a`, `r3-cc-wt-11404dc0` retired by exact name (both needed v24 first in PATH and Python 3.10, R2-12) |
| E3 | the user's final script: `approvals_reviewer` back to `guardian_subagent` (1 line), ten bridge allow rules removed from design-test; App selector was left at 帮我批准 throughout |
| E4 | `c3-rerun-results.json` written by the Codex origin into design-test, copied to the guide scratchpad and removed; `design-test-rerun-wt` and branch `ar-acc-rerun-wt` removed by the user's final script; doctor afterwards: runtime, probe (v24 from claude-entry), mailbox, host-entries, old-bridges `ok`; warnings only codex-approval (guardian, restored) and the round-2 identity `ar-acc-round2-design-claude-wt` |
| E5 | Spec Guard 0.51.2 on both hosts |
