# Authorized session delegation host-creation preflight — 2026-10-03

Plan: [`plan.md`](plan.md)

Status: **Task 1 passed with mandatory adapter constraints**. This is a go-ahead for the
authorization/state-machine slice, not a release acceptance and not evidence for A10 native
promotion. The run started from remote-default-branch commit
`861dce74246bbee55ab553c6a02ec9a6fa4efaca` after Proposal promotion proof succeeded.

The run used an owner-only disposable mailbox and a disposable Git repository for the Codex
path. Claude Code non-interactive work was first checked in that disposable repository; its
background path correctly stopped at the host's project-trust boundary, so the background
lifecycle was completed in the already trusted repository worktree without reading or changing
project files. No real Local ticket, normal collaboration mailbox, transport selector, global
Claude/Codex setting, remote system, or hidden bridge worker/review/orchestration tool was used.

## Host facts

| Fact | Result | Evidence |
| --- | --- | --- |
| Codex binary provenance | 通过 | App-managed `current` resolved to Codex CLI `0.160.0`; the older PATH-selected `0.154.0` was not invoked. |
| Claude Code provenance | 通过 | `claude --version` returned `2.1.288`. |
| Model selection | 通过 | No `model`/`--model` field was sent. Codex resolved the current configured default to `gpt-5.6-sol`; Claude resolved its default to `claude-opus-5`. These observed defaults are facts, not hard-coded requirements. |
| Backend containment | 通过 | The selected collaboration backend remained `native`; only a private mailbox path was passed to a private server process. No runtime start, backend switch, or normal mailbox access occurred. |

## Claude Code → Codex

| Check | Result | Evidence |
| --- | --- | --- |
| Create exact target | 通过 | App Server `initialize` → `thread/start` → `turn/start` created one saved thread at the disposable repository and returned its exact thread identity. No title or project-name lookup was used. |
| Permission result | 通过 | The request and response used read-only sandbox plus `approvalPolicy=never`; the isolated communication server alone used an explicit per-server approval mode. Source and Git state stayed unchanged. |
| Restricted communication catalog | 通过 | Initial inventory exposed inherited user MCP/connectors. The hardened prototype then disabled Apps, plugins, browser/computer use and multi-agent features, enumerated the exact app-managed binary's configured MCP servers, reproduced only their non-secret transport identities as disabled entries, and enabled only the ten communication tools on the private server. `mcpServerStatus/list` showed tools only on that server; hidden worker/review/orchestration tools were absent. |
| Exact registration | 通过 | Codex `0.160.0` did not expose its App Server thread ID to the MCP child. The controller therefore injected the exact ID returned by `thread/start` into the host-delivered initial envelope; `bridge_register` stored that exact target. No user-supplied ID was accepted. |
| Same-thread second turn | 通过 | `thread/resume` returned the same exact identity and a second `turn/start` completed. The turn read the Claude-originated mailbox item and saved one reply. |
| Mailbox wake | 失败 | The durable Claude→Codex message was saved, but native wake reported `pending/offline` because the App Server process was no longer a connected Codex local target. This is not reported as delivery or execution. |
| Supported continuation | 通过 | The controller resumed the exact saved App Server thread, and that thread read the durable message. The product adapter must own this continuation path; it must not wait for or claim native Codex wake. |
| Host visibility | 通过 | `thread/list` with all official source kinds returned both created test threads with Codex `0.160.0`, the exact disposable cwd/baseline, and the configured default model. The host classified them as Codex Desktop/VS Code-originated saved threads. |
| Stop/cleanup | 通过 | Both exact test threads were archived with `thread/archive`; the active list was empty and the archived list contained the recoverable records. |

## Codex → Claude Code

| Check | Result | Evidence |
| --- | --- | --- |
| Disposable untrusted project | 环境不可用 | `claude --background` stopped at `Workspace not trusted`. The run did not accept trust, edit config, or bypass the prompt. Non-interactive `--print` in the same disposable repository did complete a restricted read and exact registration, proving the MCP path separately. |
| Trusted-project creation | 通过 | `claude --background` created a named session in the already trusted repository worktree and returned an exact session identity; `claude agents --json --all --cwd …` listed it. |
| Permission result | 通过 | The session used `--restricted`, `--permission-mode dontAsk`, `--permission-prompts none`, `--strict-mcp-config`, a private no-token MCP config, an explicit communication-tool allowlist, and explicit hidden-tool denials. It did not read or change project files. |
| Exact registration | 通过 | `bridge_sessions` identified the current Claude session and `wake: "auto"` bound the same identity. The adapter must remove an inherited `CODEX_THREAD_ID` before launch; without that hygiene the MCP process can observe the origin Codex identity as unrelated ambient state. |
| Second automatic wake | 通过 | A Codex-originated mailbox send caused a new turn in the original bound Claude background session. The session saw the exact marker and correctly refused to acknowledge or reply because its host-delivered envelope prohibited those actions. |
| Same-session resume after stop | 通过 | `claude stop <short-id>` stopped the exact session. `claude --background --resume <exact-id>` with no option overrides restored the same identity and its saved restricted options; the next turn read the durable inbox item without acknowledging it. |
| Resume with repeated options | 失败 | Resuming a still-owned background session while repeating launch options created a copy with a new identity. The copy was detected and removed. The adapter must reconcile the returned identity and must not treat this host behavior as same-session continuation. |
| Stop/cleanup | 通过 | The original and accidental copy were stopped/removed by their exact returned IDs. The disposable project's Claude transcript state was dry-run scoped and then purged; no other project state was selected. |

## Cross-host result

- Claude Code → Codex: message persistence, exact recipient resolution, same-thread read, and result
  send passed. Native Codex wake did not; control-plane `thread/resume` is the required continuation
  primitive.
- Codex → Claude Code: durable send and actual background turn delivery passed. The bridge receipt
  remained `unknown` because the upstream adapter does not replay or confirm receipt, so the stored
  wake row alone is not treated as proof; the recipient transcript is the host evidence.
- A Claude background session can be created only for a project already trusted by Claude Code.
  An untrusted target is a truthful held prerequisite that requires the user to establish trust in
  that host; the module must never accept trust or edit global configuration on the user's behalf.

## Required implementation constraints

1. Before starting Codex, resolve the app-managed binary and enumerate that exact binary's MCP
   configuration. Build one process-local config that disables every inherited server by its
   non-secret transport identity, disables Apps/plugins/browser/computer-use/multi-agent features,
   and enables only the private communication server. Inventory or config drift fails closed.
2. The Codex controller owns the exact thread ID returned by `thread/start`, injects it into the
   initial host-delivered envelope, and uses `thread/resume` for later authorized turns. The
   mailbox's Codex wake state remains separately observable and must not be promoted from offline.
3. The Claude launcher strips inherited Codex session variables. A live background target is
   continued by its supported native ping; after an exact stop, resume it with its saved options
   and verify the returned ID. Repeating launch options can fork and must be reconciled.
4. Claude project trust is a prerequisite, not a permission the adapter grants. Mandatory trust or
   permission prompts are reported as held/environment unavailable until the user resolves them.
5. Both adapters omit model selection, preserve delegation depth zero, expose only communication
   tools, and keep ordinary mailbox text outside the authorization boundary.

## Commands and outcomes

| Command/evidence class | Result |
| --- | --- |
| App-managed `codex app-server --stdio`; `initialize`, `thread/start`, `turn/start`, `thread/resume`, `thread/list`, `thread/archive` | 通过 |
| `mcpServerStatus/list` before catalog hardening | 失败 — inherited external tools were visible; this produced constraint 1. |
| `mcpServerStatus/list` after process-local inventory/disable hardening | 通过 — only the private communication server had callable tools. |
| `claude --print --output-format json --session-id …` in disposable repository | 通过 |
| `claude --background` in disposable untrusted repository | 环境不可用 — workspace trust required. |
| Restricted `claude --background` in trusted worktree; `claude agents --json`; native wake | 通过 |
| `claude --background --resume …` with repeated options | 失败 — host created a copy; copy removed. |
| `claude stop …`; no-override `claude --background --resume …`; exact `claude rm …` | 通过 |
| Repository source tests | 未运行 — this preflight changed documentation only; repository checks run with the resulting diff. |

## Verdict

Proceed to Task 2. Task 1 is complete for the supported same-Mac path with the constraints above.
The no-go conditions remain: an untrusted Claude target without user-established trust, inability
to construct the restricted Codex process catalog, any need for a user-supplied hidden ID, or any
request to weaken global host configuration. Native/XATS promotion gates and the independent A10
two-version/two-host/upstream-revision/no-open-P1/P2 evidence remain unchanged.
