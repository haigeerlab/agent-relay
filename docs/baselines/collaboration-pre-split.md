# Collaboration pre-split baseline

Recorded 2026-10-06 before splitting the collaboration capability out of Spec Guard. Every later
"behaves the same as before" judgement is made against this file, not against memory.

## Source and rollback point

| Item | Value |
|---|---|
| Source commit | `54d0426f5883934914b2a8b3832c5e36ab47e222` (`main` = `origin/main`) |
| Rollback branch | `backup/pre-collaboration-split` → same commit (local only) |
| Plugin version | 0.49.0 (Claude and Codex manifests) |
| Guiding Spec Guard install | Claude `spec-guard@spec-guard-marketplace` 0.49.0, `gitCommitSha ca273f90`, user scope; Codex `spec-guard@spec-guard-marketplace` 0.49.0 from `~/.codex/.tmp/marketplaces/spec-guard-marketplace` |

## Host and runtime versions

| Component | Version | Evidence |
|---|---|---|
| macOS | 15.7.3 | `sw_vers -productVersion` |
| Claude Code | 2.1.289 | `claude --version` |
| Codex (PATH) | codex-cli 0.160.0 | `codex --version` |
| Codex (app-managed) | codex-cli 0.160.1 | `~/.codex/packages/app-server-daemon/current/codex --version` |
| Node.js | v24.18.0 | `node --version` |
| Python | 3.10.7 | `python3 --version` |
| Native bridge runtime | upstream `WebisityStudio/claude-codex-mcp-bridge` @ `8f12c880cfdba73812b6ab7bc0f373fc467e0343` (MIT); upstream HEAD identical | `native_collaboration_runtime.py status` → `ready`; `gh api …/compare` → `identical` |

## Prerequisites

| Question | Result | Evidence |
|---|---|---|
| Codex can add a marketplace from a local path and install from it | Yes | In an isolated `CODEX_HOME`: `codex plugin marketplace add <worktree>` → added; `codex plugin add spec-guard@spec-guard-marketplace` → installed 0.49.0. Real `~/.codex` unchanged afterwards. |
| `gh` is logged in | Yes | `gh auth status`: `haigeerlab` active, scopes include `repo`, `workflow` |
| Claude Code plugin-to-plugin dependency | Supported | `plugin.json` `dependencies` (string or `{name, marketplace, version}`), installs missing dependencies; a dependency from another marketplace needs `allowCrossMarketplaceDependenciesOn` in the root marketplace, otherwise the dependent plugin fails to load. https://code.claude.com/docs/en/plugins-reference#dependencies , https://code.claude.com/docs/en/plugins/dependencies |
| Codex plugin-to-plugin dependency | Not supported | `RawPluginManifest` in `codex-rs/core-plugins/src/manifest.rs` at tag `rust-v0.160.0` has only `name, version, description, keywords, skills, mcpServers, apps, hooks, interface, extensions`; no dependency field. https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core-plugins/src/manifest.rs |

## Automated suites (pre-split)

| Suite | Result | Cases | Duration |
|---|---|---|---|
| `/bin/bash scripts/validate.sh` | pass (exit 0, "校验通过 ✅") | 865 output lines | 207 s |
| `/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh` | pass | 151 | 38 s |
| `/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh` | pass | 26 | 4 s |

Collaboration test files (each run directly with `python3 -B`, all `OK`):

| File | Tests |
|---|---|
| `test_native_collaboration_runtime.py` | 9 |
| `test_native_collaboration_adapters.py` | 8 |
| `test_native_collaboration_retire.py` | 6 |
| `test_native_only_collaboration.py` | 3 |
| `test_native_collab_entry.py` | 5 |
| `test_collab_entry.py` | 9 |
| `test_session_routing.py` | 16 |
| `test_session_routing_entry.py` | 19 |
| `test_session_delegation.py` | 21 |
| `test_session_delegation_backend.py` | 4 |
| `test_session_delegation_claude.py` | 50 |
| `test_session_delegation_codex.py` | 22 |
| `test_session_delegation_recovery.py` | 18 |
| **Collaboration total** | **190** |
| Shared: `test_host_config_removal.py` | 10 |
| Shared: `test_skill_entrypoints.py` | 11 |

`evals/` contains no collaboration-specific eval; `evals/codex-plugin-smoke.sh` is the generic consumer smoke
and is covered by `validate.sh`.

## Local state present on this Mac (structure only, no message bodies read)

| Path | Contents | Counts |
|---|---|---|
| `~/.spec-guard/native-collaboration/` | pinned bridge checkout + `dist/server.js`, `mailbox/bridge.sqlite`, `mailbox/backups/` (7 files), `data/`, `manifest.json`, `host-config-backup.v7xZtz/` (copies of `claude-settings.json`, `claude.json`, `codex-config.toml`; not created by Spec Guard code) | 72 messages, 50 agents; wake jobs: accepted 1, cancelled 17, read 31 |
| `~/.spec-guard/session-delegation/delegation.sqlite` | tables `delegations`, `authorizations` | 3 / 3 rows |
| `~/.spec-guard/collaboration/` | retired XATS transport history (`messages.sqlite` + WAL, `runtime.json`, `token`, logs) | not opened |
| Claude user MCP | `spec-guard-native-collaboration` → `node …/dist/server.js`, `BRIDGE_DB_PATH=…/bridge.sqlite`, connected | `claude mcp get` |
| Codex config | `[mcp_servers.spec_guard_native_collaboration]` + `.env` at `~/.codex/config.toml:371` | grep |

## Phase 0 decisions (user, 2026-10-06)

| Decision | Choice |
|---|---|
| New plugin name | `agent-relay` |
| Code migration | `git filter-repo` path-list filter with path renames (keeps per-file history) |
| Mailbox core ownership for hardening | Bring the pinned upstream bridge into `agent-relay` and maintain it there, keeping MIT attribution (direction only; confirmed in the capability map review) |

## Real-host acceptance (pre-split, 2026-10-06)

Run against the installed guide plugin (Claude and Codex `spec-guard` 0.49.0) and the pinned native runtime,
all sessions in the main checkout `/Users/vilin/Documents/haigeerlab/spec-guard-plugin` (`main` = `54d0426`).
Message bodies outside the synthetic test identities were not read. All test identities used the
`sg-baseline-*` prefix or were created by the delegation controller (`sg-dl-*`).

### Sessions

| Role | Host | How it ran |
|---|---|---|
| A1, B1 | Claude Code 2.1.289 background sessions | `claude --bg --permission-mode default --tools "ListAgents,SendMessage"` plus a session-only `--allowedTools` list of the ten mailbox tools; no settings file changed |
| E3 | Claude Code background session (delegation origin) | `--permission-mode dontAsk`, Bash limited to git read-only, `date`, `printf` and the installed controller |
| C, D | Codex App threads (app-managed codex-cli 0.160.1), project `spec-guard-plugin` | created through the App UI, worktree mode on (`/Users/vilin/.codex/worktrees/2a02/spec-guard-plugin`, detached `54d0426`) |

Operator setup errors, recorded so they are not mistaken for product behavior: the first A/B sessions were
started with `--tools ""`, which removes `ListAgents`/`SendMessage` (A reported `SG_CC_NO_TOOLS`); the first two
delegation origins (E, E2) stalled on host permission prompts (a shell variable; `git -C` not matching the
allow rule) before any controller call. All were stopped and replaced.

### Results

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Register four wake-bound identities (2 Claude `auto`, 2 Codex `{app, sessionId}`) | Pass | `bridge_agents` rows for `sg-baseline-{A1,B1}-claude`, `sg-baseline-{C,D}-codex` with wake targets |
| 2 | Claude → Claude, host-native: A1 → B1, B1 replies | Pass | `SendMessage`; B1 reply `SG_CC_PONG_1`; A1 → operator `SG_CC_A1_GOT_PONG_1` |
| 3 | Claude → Claude, reverse and second round: B1 → A1, A1 replies | Pass | `SG_CC_PONG_2`; B1 → operator `SG_CC_B1_GOT_PONG_2` |
| 4 | Codex → Codex, host-native: D starts two turns on C | Pass (transport) | D used `list_threads`, `send_message_to_thread`, `wait_threads`; both turns completed and both replies were read. Reply text was not the requested token because C's standing prompt told it to handle only its bridge inbox (test-design defect, not product behavior) |
| 5 | Claude → Codex via mailbox, Codex woken, reply wakes Claude | Pass | A1 → D msg #77 (no warnings); D woken, replied `SG_XC_D_PONG_1` #78; A1 woken, acked |
| 6 | Codex → Claude via mailbox, same idle Claude woken twice | Pass | D → B1 #79 → reply #80 `SG_CX_B1_PONG_1`; #81 → reply #82 `SG_CX_B1_PONG_2`; B1 wake jobs 56, 58 `read`, `attempts=1` each |
| 7 | Claude → Codex delegation (E3 origin), six steps | Pass | create `sg-dl-review` safe-review → `state=completed`, `transport=spec-guard-bridge`, `resultDelivery=enqueued`; result #73 woke E3; same-session round 2 #74 (`0.49.0`); read-only negative refused, #75, clean tree; same-name → `session-name-ambiguous` with `9b1ad0`/`812a33`, each queryable with `--disambiguator`; both cancelled |
| 8 | Codex → Claude delegation (D origin), first attempt | Held (correct) | `state=held`, `prerequisite=project-allow-rules`: main checkout had no allow rules for the ten mailbox tools |
| 9 | Codex → Claude delegation, after a user-written git-ignored `.claude/settings.local.json` with exactly the ten `requiredAllow` tools (preflight `ready=true`) | Partial | create `sg-dl-claude` → `state=created`, `resultDelivery=pending`; result #83 from `sg-dl-claude-7bd8a30d` read and acked (pass). **Round 2 `continue` returned `state=held`, `prerequisite=target-busy` while `hostStatus=idle`; reproduced on one retry while `ListAgents` showed the target idle (fail).** Read-only negative not run. Same-name: `27f0de`/`7bd8a3` ambiguity (pass); cancel `7bd8a3` → `cancelled` (pass); cancel `27f0de` → `unknown` |
| 10 | Unbound session is not woken | Not separately exercised | D was unbound (`wake: null`) between steps and received nothing; no message was sent to it in that window |

### Findings for the interface document and hardening

1. **Codex auto-review is not detected.** `~/.codex/config.toml` has `approvals_reviewer = "guardian_subagent"`
   (AI reviewer decides approvals). C and D bound wake under it without any check. By user decision this counts
   as auto-approval; the Codex App approval selector was switched to 请求批准 (manual) for the remaining tests
   and restored to 帮我批准 afterwards. The selector is app-wide, not per thread.
2. **Delegation `--expires-at` needs integer epoch seconds**; an ISO string exits 2. The skill does not say so.
3. **A held create still persists a named envelope** (`27f0de`), which later makes the name ambiguous and
   cannot be cancelled cleanly (`unknown`).
4. **Claude-target second round reports `target-busy` while the host says idle** (item 9). The 2026-10-04
   record had this passing on Claude 2.1.288; treat as a regression or host change to investigate.
5. **Wake job state stops at `read`** with detail "work is not yet acknowledged" even after `acknowledgedAt`
   is set on the same row.
6. **Background Claude sessions hang forever on any permission prompt** (`default` mode); `dontAsk` avoids it.
7. **Codex manual approval prompts for every mailbox tool call** of a woken turn (`bridge_inbox`, `bridge_send`,
   `bridge_ack`, controller runs); a woken Codex turn waits for a human under 请求批准. The App also offers a
   "reduce approval prompts?" dialog whose Enter default switches to 帮我批准.

### Cleanup

- Background sessions A, B, A1, B1, E, E2, E3 stopped; delegated sessions cancelled (`9b1ad0`, `812a33`,
  `7bd8a3`; `27f0de` unknown, never launched).
- Identities retired with history kept (12): `sg-baseline-{A,B,A1,B1,E,E2,E3}-claude`,
  `sg-baseline-{C,D}-codex`, `sg-dl-review-01a1115{a,b}`, `sg-dl-claude-7bd8a30d`.
- Codex approval selector restored to 帮我批准; thread D archived; thread C (「注册基线测试唤醒身份」) left for the
  user to archive.
- Temporary `.claude/settings.local.json` in the main checkout removed by the user; `.claude/` again holds only
  `worktrees/` and `git status` is clean.
- Guide plugin unchanged after the run: Claude `spec-guard` 0.49.0 `ca273f90`, Codex `spec-guard` 0.49.0.

The previous live records (`tasks/collaboration-messaging/native-repeat-wake-acceptance-2026-10-03.md`,
`tasks/host-native-session-routing/live-acceptance-2026-10-04.md`,
`tasks/authorized-session-delegation/live-acceptance-2026-10-04.md`) remain for comparison only.
