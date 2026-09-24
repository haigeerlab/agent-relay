# Plan: optional Claude Code CLI tmux wake

Module: [`../../spec/collaboration-messaging.md`](../../spec/collaboration-messaging.md)
Tasks: [`claude-tmux-wake-tasks.md`](claude-tmux-wake-tasks.md)

This is an alternative to the blocked third-party Channel preview path; it does not replace the
unfinished Channel research plan.

Status: launcher, service-path generation, and documentation pass tests. After the user approved
refreshing the managed LaunchAgent, a real idle Claude CLI session received a short tmux wake hint,
read the message, and replied. See [`claude-tmux-wake-acceptance.md`](claude-tmux-wake-acceptance.md).

## Goal

Give a user one explicit command to start a Claude Code CLI session in tmux so the pinned local XATS
runtime can bind that session and send a short inbox hint when a peer writes to it. Ordinary Claude
sessions remain mailbox-only. Native Codex Desktop and ChatGPT in Chrome are unchanged.

## Design

- Add an opt-in `--tmux-wake` mode to the existing Claude launcher. Outside tmux, it attaches to a
  new uniquely named tmux session running the same launcher. Inside tmux, it runs Claude normally.
- Pass the child command as separate arguments, not through a shell string. Do not place the bearer
  token in tmux commands, session names, project files, or process arguments.
- Keep the daily `collab` self-registration; the current Claude session supplies its own `$PPID` as
  `ui_pid`. XATS 0.8.6 verifies PID → TTY → pane before binding and before a tmux poke. Neither the
  launcher nor another process may register a session on its behalf.
- The opted-in user LaunchAgent must include the installed tmux directory on the daemon's PATH;
  otherwise XATS cannot bind a pane even when Claude started inside tmux. Source changes alone do
  not restart or rewrite an installed LaunchAgent; that remains an explicit operator action.
- A poke is a short inbox hint, not the message body or a permission grant. Report mailbox write,
  poke attempt, and recipient read as separate facts. Do not infer that Claude processed a message
  from tmux's successful paste alone.
- Do not use the third-party development Channel flag, change Codex Desktop's app-server mode, or
  install another messaging service.

## Acceptance

1. No opt-in: launch command and behavior are unchanged.
2. With opt-in: one command creates a tmux-hosted Claude CLI session; a session already in tmux is
   not nested. Missing tmux or a noninteractive terminal fails clearly before starting Claude.
3. Tests prove argument forwarding, no-shell command construction, no token in arguments, unique
   session names, and default-off behavior.
4. A real idle Claude CLI session self-registers, is bound to its own pane, receives one benign
   message, calls `get_inbox` without a manual prompt, and can reply. If the host cannot demonstrate
   this, record the exact limit and leave active wake unverified.

## Host finding

The first real session started in a tmux pane and self-registered, but the existing user LaunchAgent
PATH omitted the Homebrew directory containing tmux. XATS returned `spawn tmux ENOENT` and kept the
agent mailbox-only. The source now includes tmux's directory in future explicit service enablement.
After explicit user approval, the installed service was refreshed and the second real session passed
the end-to-end wake, read, and reply check.

## Verification

```text
python3 -B plugins/spec-guard/hooks/test_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_collab_entry.py
/bin/bash scripts/validate.sh
git diff --check
```

## Safety and rollback

The user explicitly selects this CLI mode. tmux can type into the target terminal, so only XATS's
verified pane binding and short-hint path may be used; no plugin-owned `send-keys` or message-body
injection is added. Exit Claude to end the tmux session. Remove the optional flag to return to the
ordinary mailbox path. A one-time refresh of an already installed managed LaunchAgent was needed
on the tested host to expose tmux to XATS; no new service or project configuration was added.

Primary sources: [XATS](https://github.com/jtianling/cross-agent-teams-mcp),
[tmux manual](https://man.openbsd.org/tmux),
[Claude Channels](https://code.claude.com/docs/en/channels).
