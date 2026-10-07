# Acceptance record: acceptance-kit-round2 and adapter-node (2026-10-08)

Real-host acceptance of `acceptance-kit-round2` (PR #14, main feaa0e8; D53–D57 for R2-3, R2-5, R2-8, R2-11, R2-12)
and of `adapter-node` (PR #15, main 546fdf7; D58 for R2-13, found during this acceptance). See
[2026-10-07-round2-rerun.md](2026-10-07-round2-rerun.md) for R2-11 and R2-12.

## Run

| Field | Value |
|---|---|
| agent-relay commit | feaa0e8, then 546fdf7 (main checkout fast-forwarded each time; Codex plugin cache refreshed with `codex plugin add agent-relay@agent-relay-marketplace`) |
| Spec Guard | 0.51.3 on both hosts |
| Claude Code / Codex | 2.1.291 / codex-cli 0.160.0 |
| Shell environment | "hostile" PATH: `python3` → `/usr/bin/python3` 3.9.6, then nvm v12.22.12, then system directories; no `--node` or `--npm` unless a row says otherwise. `~/.claude.json` pins nvm v24.18.0 for the agent-relay entry |
| Permission changes | none |

## Results

| Id | Steps taken | Result | Evidence |
|---|---|---|---|
| D54 / R2-5 stale copies | before refreshing anything: `preflight.sh --design design-test` from an export of feaa0e8 (v24 first so the `codex` CLI runs); then main checkout fast-forwarded, `codex plugin add`, preflight from the main checkout | pass | before: Claude `loaded …/agent-relay/plugins/agent-relay STALE (… update that checkout to this commit)`, Codex `loaded ~/.codex/plugins/cache/…/0.1.0 STALE (refresh: codex plugin add agent-relay@agent-relay-marketplace)`; the seven Claude install records `not loaded: a directory marketplace is read from its source`. After: both `current` (tree b2bf5dda33b5; again `current` at 546fdf7, tree aa765b034640) |
| D54 under v12 | same preflight with the hostile PATH | pass (degraded) | Codex line `unknown (…codex.js:279)`: the `codex` CLI itself fails on Node 12 (`SyntaxError: Unexpected reserved word`), so preflight reports unknown instead of a verdict; Claude line and lists unaffected |
| D55 / R2-8 allow lists | preflight output | pass | `allow (base)`: ListAgents, SendMessage and the ten mailbox tools, one quoted argument each; `allow (routing)`: base + `"Bash(python3 -B /Users/vilin/Documents/haigeerlab/agent-relay/plugins/agent-relay/hooks/session_routing.py select *)"` + `"Read(//Users/vilin/Documents/haigeerlab/design-test/**)"` |
| D55 selector rule | `claude -p --permission-mode dontAsk --allowedTools "<selector rule>"` asked to run the selector four ways, then controls | pass | allowed: heredoc, pipe from `printf`, `< in.json`, no input; denied: `validate-outcome` with a heredoc, the heredoc followed by `touch pwned.txt` (no file made); without the rule the heredoc form is denied |
| D56 / R2-3 launch line | preflight output | pass | `claude "<prompt>" --bg --permission-mode dontAsk --allowedTools <base or routing list>` with the prompt-first note and the `--tools ""` warning |
| D57 / R2-12 retire | two identities `ar-acc-r2kit-a`, `-b` registered by two `claude -p` sessions; hostile PATH: `native_collaboration_retire.py --name ar-acc-r2kit-a --confirm-retire` | pass | `{"name": "ar-acc-r2kit-a", "state": "retired"}`, rc 0 (round 2: refused with the PATH node) |
| D57 / R2-12 cleanup.sh | hostile PATH: `cleanup.sh r2kit` before and after the retire, then `--confirm`, then preview | pass | preview 2 → 1 (retired one excluded) → `ar-acc-r2kit-b: retired`, rc 0 → 0 live identities (round 2: "unable to open database file" on 3.9) |
| D57 / R2-12 reinstall around history | hostile PATH: `uninstall-codex`, `native_collaboration_runtime.py uninstall --confirm`, `install` | not run on the real host | runtime uninstall refused: "a bridge server of this runtime is running; close every session using the mailbox first" (correct: this and other sessions were open); history hash unchanged; Codex entry re-attached with `--node`. The user accepted the module's live check in a temporary home (v12 first, `/usr/bin/python3`, entry pinning v24, no `--node`/`--npm`: `install` ready, retire, uninstall and reinstall with mailbox bytes unchanged, `cleanup.sh` preview and `--confirm`) |
| R2-13 found | hostile PATH, temporary `--codex-config`: `install-codex` without `--node` at feaa0e8 | fail → R2-13 | rc 0, `command = "/Users/vilin/.nvm/versions/node/v12.22.12/bin/node"` written while the Claude entry pins v24; no version check. `uninstall-codex` under v12 removes a table written with v24 (not affected) |
| D58 / R2-13 temporary config | PR #15 head 10821e8 exported, hostile PATH, temporary configs | pass | Claude entry pinning v24 → `command = "…/v24.18.0/bin/node"`; empty `claude.json`, no Codex table, only v12 → rc 2 `node-too-old: …/v12.22.12/bin/node (PATH) is Node v12.22.12 …`, config 0 bytes, no backup; `uninstall-codex` under v12 removes the table |
| D58 / R2-13 real host | 546fdf7, hostile PATH: `uninstall-codex --confirm-uninstall`, `install-codex` (no `--node`), `doctor` | pass | `[mcp_servers.agent_relay] command = "/Users/vilin/.nvm/versions/node/v24.18.0/bin/node"`; doctor: runtime, probe (v24 from claude-entry, 17 tools), mailbox (schema 5), host-entries, old-bridges `ok`; warnings only codex-approval (`guardian_subagent`, the machine's normal setting) and the round-2 identity `ar-acc-round2-design-claude-wt` |

## Findings

R2-13. **Host adapters pinned the PATH node** (product; fixed by `adapter-node`, D58). `native_collaboration_adapters.py`
defaulted `--node` to `shutil.which("node")`, so `install-codex` / `install-claude` (and the printed `codex` / `claude`
fragments) skipped the D50 order and wrote a Node too old for `node:sqlite` into host configuration. Fixed and
verified above.

## Cleanup

| Item | Result |
|---|---|
| Test identities | `ar-acc-r2kit-a`, `ar-acc-r2kit-b` retired |
| Host configuration | Codex table re-attached with v24 (unchanged in substance); no permission or approval setting changed |
| Backups left | `~/.agent-relay/backups/` 20261007T163248Z, 20261007T163259Z-1, 20261007T164520Z, 20261007T164520Z-1 hold only temporary test configs; the D57/D58 real-host runs added the usual host-config backups. Deletion is the user's |
| Earlier leftovers | `ar-acc-round2-design-claude-wt` (1 unacked) and envelopes `r2-cx-review` e168ea/269770 unchanged |

## Verdict

acceptance-kit-round2 and adapter-node pass against their acceptance criteria; with the user's acceptance of the
temporary-home evidence for the reinstall row, no open finding blocks the hardening release.
