# Plan: optional Claude Code channel wake

Module: [`../../spec/collaboration-messaging.md`](../../spec/collaboration-messaging.md)
Task list: [`claude-wake-tasks.md`](claude-wake-tasks.md)

This is a local task list while GitHub Release and tracker access are unreliable; it does not
replace or update a Proposal Issue.

Status: launcher hardening and documentation passed; active wake remains unverified and blocked
at the vendor's development-channel warning.

## Goal

Let a user explicitly start a Claude Code CLI session that can be awakened by a Spec Guard
collaboration message, while ordinary Claude sessions and native Codex Desktop keep their current
mailbox behavior. Preserve ChatGPT in Chrome and the existing private same-Mac runtime.

## Current baseline

The plugin already generates a pinned XATS channel MCP entry and has an opt-in Claude launcher using
`--enable-channel-wake`. Existing tests cover the generated configuration and command line, but no
record proves that an incoming message reaches a real running Claude Code session without a manual
inbox read. This work tests whether that path can be safely exposed; it does not create another
message server.

## Host finding

A real Claude Code CLI launch reached Anthropic's development-channel warning. It explicitly says
not to use that flag for channels downloaded from the internet. The pinned XATS channel is a
third-party package, so the test exited at that prompt. No wake was attempted or observed. Public
operator guidance must not present this path as generally enabled while this warning stands.

## Decisions and boundaries

- Enable the research-preview channel only for a newly launched Claude Code CLI session after an
  explicit user choice. Never change normal Claude or Codex startup automatically.
- Keep XATS `0.8.6`, the loopback listener, private token files, and the mailbox fallback. A channel
  event is not evidence of a human authorization or of a completed task.
- Do not enable permission bypass or permission relay. Never claim a message was processed merely
  because it was stored or a channel notification was written.
- Do not modify Codex Desktop's app-server mode or ChatGPT in Chrome integration.
- Scope this slice to the Claude Code CLI. Desktop and editor-hosted Claude sessions need separate
  host verification and are not promised active wake here.

## Implementation order

1. Tighten the existing opt-in launch contract and test the default-off and explicit-on paths,
   including option-override rejection and no-secret configuration.
2. Give operators one exact enable, verify, stop, and fallback path in the existing collaboration
   documentation/skill. State the research-preview and account-policy limitations.
3. Run focused and repository validation, then attempt one real-host message into an idle Claude CLI
   session using a temporary identity. Record whether the session reacted without an inbox prompt;
   if the preview is unavailable, report that boundary rather than marking wake as passed.

## Acceptance

- The default launcher remains mailbox-only; the preview channel appears only with explicit opt-in.
- Generated config and process arguments contain no bearer token; caller-supplied MCP/channel flags
  cannot replace the wrapper's selected channel.
- A real Claude Code CLI session either demonstrates unsolicited wake and reply or yields a precise,
  reproducible unsupported/blocked result. Mailbox delivery still works in either case.
- Codex Desktop configuration and startup are unchanged; ChatGPT in Chrome remains available.

## Verification

```text
python3 -B plugins/spec-guard/hooks/test_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_collab_entry.py
/bin/bash scripts/validate.sh
/bin/bash evals/codex-plugin-smoke.sh --selftest
git diff --check
```

## Risks

- Claude Channels are a research preview and may be unavailable by account or organization policy.
- The development flag is not an approved distribution path for a downloaded third-party channel;
  general-user wake needs an applicable official approval route or a separate security decision.
- A successful MCP connection does not prove Claude accepted channel notifications. The real-host
  test must observe the target session, not infer wake from the sender's `send_message` result.
- The channel carries untrusted peer text into a live agent. Existing permission prompts and the
  message-is-not-authorization boundary must remain intact.

Official references: [Claude Channels](https://code.claude.com/docs/en/channels),
[Channels reference](https://code.claude.com/docs/en/channels-reference).
