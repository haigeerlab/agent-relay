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

## Real-host acceptance (pre-split)

Status: **not yet run in this baseline** — waiting for the user to open the sessions listed in the Phase 0
checkpoint report. The most recent prior live records, kept for comparison only, are:

- `tasks/collaboration-messaging/native-repeat-wake-acceptance-2026-10-03.md`
- `tasks/host-native-session-routing/live-acceptance-2026-10-04.md` (Claude 2.1.288, Codex 0.160.0)
- `tasks/authorized-session-delegation/live-acceptance-2026-10-04.md` (Claude 2.1.288, Codex 0.160.0)

Host versions have moved since (Claude 2.1.289, app-managed Codex 0.160.1), so those records do not serve as
this baseline.
