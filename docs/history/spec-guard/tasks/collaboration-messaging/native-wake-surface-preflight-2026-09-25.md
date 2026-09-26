# Native wake tool-surface preflight — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **partial evidence, Task 2 not passed**. Source was read in an isolated temporary checkout;
no package was installed into Claude, Codex, or Spec Guard, and no host configuration changed.

## Bridge source finding

At audited checkout `WebisityStudio/claude-codex-mcp-bridge` commit
`8f12c880cfdba73812b6ab7bc0f373fc467e0343`, `src/server.ts` registers all mailbox tools and
also `ask_codex`, `review_with_codex`, `bridge_orchestrate_codex`, `bridge_continue_codex`,
`bridge_orchestration_wait`, and `bridge_orchestration_status` without a mailbox-only condition.
The same file detects `CODEX_THREAD_ID` only if it reaches the MCP server process; the previous
isolated host trial's `bridge_sessions.thisSession` was null. An Agent-side command can observe its
own task ID on this host, but exact multi-task binding is still Task 1's unpassed gate.

Codex's host configuration supports an `enabled_tools` list. Claude's **bare-name** `deny` rule
(for example, one complete `mcp__<server>__ask_codex` name) removes the named tool from Claude's
context and blocks its use; an `allow` rule alone does not hide other tools. This makes exact
host-native restrictions the first option, without another proxy. The rules must be scoped to
Spec Guard's own MCP server name and proved in both actual host tool catalogs. A prompt telling
the Agent not to call worker tools is insufficient.

## Open-source filtering option, not yet adopted

The MIT [`pro-vi/mcp-filter`](https://github.com/pro-vi/mcp-filter) checkout at
`1a15a3ca33f8d5dc7b19fb55402249c4d5d1a45f` has an exact-name allowlist. Its source builds
`tools/list` from that allowlist and rejects `tools/call` names outside the exposed map. It requires
Python 3.10+ and adds a second local runtime layer. It has **not** been tested with this bridge or
either real host here. Use it only if exact host-native restrictions fail and the extra layer can
be justified; an upstream mailbox-only mode would be preferable. Audit and pin the filter before
considering it as an internal dependency. It must not become a second user-installed plugin.

## Remaining gate

Prove a pinned configuration where ordinary Claude Code and Codex Desktop show only the intended
communication tools and an attempted worker-tool call is rejected. First test Codex `enabled_tools`
and Claude exact bare-name `deny`; if a proxy is later needed, check that it does not change wake
delivery, private-file handling, Chrome integrations, or error reporting.
Until then, keep the existing XATS default and do not begin transport replacement.

## Follow-up: fixed-revision checks and blocked host trial

The same immutable bridge commit was cloned into an owner-private temporary directory. Node
`v22.22.0` met its `>=22.5.0` requirement. Dependencies were installed from `package-lock.json`
with install scripts disabled. `npm run check` passed typecheck, build and all **70/70** tests when
run outside the restrictive sandbox. The first sandboxed run failed only on `/bin/ps` and a test
Unix socket, both with `EPERM`; this was not treated as a product failure. `npm audit
--audit-level=high` reported **0 vulnerabilities**. These checks do not establish the safety of
future upstream commits or the behavior of the real hosts.

The attempted temporary Codex MCP addition was **rejected before any configuration write**:
the unfiltered upstream server would expose worker/orchestration tools until `enabled_tools` is
applied, and approval for that persistent user-level change was not sufficiently specific.
The user's Codex configuration was compared byte-for-byte with a private pre-attempt backup and
remained unchanged; no trial MCP entry exists. Do not retry the same write through another
command or indirect method. A future real-host trial needs an explicitly approved, atomic
communication-only configuration and a fresh permission review. Task 2 remains pending.

Sources: [bridge repository](https://github.com/WebisityStudio/claude-codex-mcp-bridge),
[Codex MCP tool selection](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[Claude tool permission semantics](https://code.claude.com/docs/en/permissions),
[MCP Filter repository](https://github.com/pro-vi/mcp-filter).
