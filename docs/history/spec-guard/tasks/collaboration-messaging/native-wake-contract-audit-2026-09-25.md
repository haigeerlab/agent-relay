# Native wake communication contract audit — 2026-09-25

Status: **same-user trust boundary chosen; not a transport go/no-go decision**. Audited the same pinned MIT bridge revision
`8f12c880cfdba73812b6ab7bc0f373fc467e0343` against the accepted
[`collaboration-messaging` Spec](../../spec/collaboration-messaging.md) and the
[`native-wake` plan](native-wake-migration-plan.md). No runtime or host configuration changed.

## What the host filters actually guarantee

- Codex `enabled_tools` is a documented MCP tool allowlist. Claude's bare-name
  `--disallowedTools` removes named tools from its model context. The earlier real-host catalog
  smokes found only ten bridge communication tools in both hosts. This is enough to keep normal
  Spec Guard users from accidentally invoking the upstream worker/review/orchestration tools
  through those hosts, subject to a fresh-host recheck after packaging.
- These host filters do **not** change the upstream server implementation or validate message-tool
  arguments. A separate same-user MCP client can still invoke any tool the upstream server
  registers. Treat the filter as a host exposure boundary, not as an authorization boundary for
  processes with access to the private SQLite mailbox.

## Session identity and acknowledgement gaps

- `bridge_register` accepts both `wake: "auto"` and an explicit `{app, sessionId}`. With an omitted
  wake target it refreshes an arbitrary registered name; with `wake: null` it can unbind that name.
  The live-session collision check prevents the common accidental takeover of a *different live
  wake binding*, as verified by the fork smoke, but it does not prove that the caller owns the
  claimed name or target.
- `bridge_send` accepts a free-form `from` name and only warns if it is unregistered.
  `bridge_inbox`, `bridge_wait`, `bridge_ack` and `bridge_outbox` accept a free-form agent name.
  The offline test's new Claude conversation could read and acknowledge the old conversation's
  mailbox by specifying its agent name. This is useful for recovery but means the current bridge
  provides **same-user cooperative routing, not per-session mailbox access control**.
- `bridge_wait` defaults `acknowledge` to `true` and marks returned messages handled before the
  caller processes them. A future `collab` adapter must either omit this tool from its normal
  path or always pass `acknowledge: false`, then explicitly acknowledge only after handling.
  Otherwise it would violate the accepted distinction between stored, read and handled.
- The explicit-hold smoke also found the bridge's automated explanation misattributed a hold to
  Bypass permissions; its `read` detail can say work is unacknowledged even after
  `acknowledgedAt` is set. A daily-use adapter must not repeat those causal claims or stale details.

## Trust-boundary decision

The current `collab` skill says only the current MCP conversation may register itself. That is a
workflow instruction, not something this upstream bridge enforces. The user chose option 1 for
this same-Mac capability; host tool filtering must not be presented as proof of per-session access
control.

**Chosen — same-user cooperative mailbox (smallest integration).** Keep bridge agent names as
routing labels, not authentication identities. The normal Spec Guard entry must bind its own
session and never ask users for IDs. Describe the trust boundary honestly, keep peer text
untrusted, require `acknowledge: false` for any wait, and report observed delivery states only.
This fits the same-Mac, one-user workflow but does not prevent another same-user process from
reading or writing an agent's mailbox. Same-user processes already share the local project files;
this is a coordination promise, not a separate security principal.

**Deferred — enforced per-session ownership.** The pinned upstream server alone cannot provide
“only this session can register/read/ack/send as itself” as a security guarantee. That would need
an audited upstream change or a local facade with a verifiable host identity; Codex's task ID was
available to the Agent in the earlier smoke but not to that MCP process. Revisit only if the
product later needs untrusted same-user processes, distinct OS users or remote transport.

No accepted Spec clause is changed by this audit. XATS stays the default. The one-step entry,
direct blocked-worker-call check, accurate failure wording and both complete Chrome workflows
remain unverified.

Sources: [Codex MCP tool policy](https://learn.chatgpt.com/docs/extend/mcp),
[Claude CLI tool restrictions](https://code.claude.com/docs/en/cli-reference),
[Claude peer-message permission boundary](https://code.claude.com/docs/en/cross-session-messaging),
[pinned bridge server source](https://github.com/WebisityStudio/claude-codex-mcp-bridge/blob/8f12c880cfdba73812b6ab7bc0f373fc467e0343/src/server.ts).
