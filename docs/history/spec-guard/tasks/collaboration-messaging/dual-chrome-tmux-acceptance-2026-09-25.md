# Dual Chrome and Claude tmux wake acceptance — 2026-09-25

Status: **passed for the tested same-Mac, opt-in Claude Code CLI tmux path**. This does not
establish active wake for native Codex Desktop, ordinary Claude CLI sessions, or every host.

## Setup and browser checks

- Tested the launcher compatibility change on its review branch; that change was subsequently
  merged to the remote default branch as PR #229.
- The existing loopback XATS service was confirmed running on the host. A temporary Claude Code
  CLI session was launched with `--tmux-wake -- --chrome`; a command-local terminal type was needed
  because the automation terminal otherwise reported `TERM=dumb`. No persistent terminal, browser,
  Desktop, or service configuration was changed.
- Claude registered from its own MCP session, bound to its tmux pane, opened a new Chrome tab at
  `https://example.com/`, read the title `Example Domain`, and closed the test tab.
- Native Codex Desktop independently used ChatGPT in Chrome to open the same public test page in
  a new tab, read the same title, and close its test tab. Neither side inspected existing tabs.

## Mailbox and wake checks

- After Claude finished its first turn and became idle, Codex sent one benign mailbox message.
  The send returned `poked: true` with no skip reason. This alone would not prove a read.
- The Claude tmux pane displayed the short inbox hint without a manual prompt. Claude then called
  its own `get_inbox`; the sender's acknowledgement was `read` after about 4.3 seconds. A separate
  delivery query reported `wake_status: delivered` and `read: true`.
- Claude replied through the mailbox, and Codex Desktop read that reply through its own inbox.
  The reply was not expected to actively wake native Codex Desktop, which remained mailbox-only.
- Both temporary identities were unregistered from their own MCP sessions, and the temporary
  Claude tmux session exited. The repository working tree was unchanged by the host test.

This acceptance distinguishes mailbox write, wake-hint dispatch, recipient read, and reply. It
does not enable the preview Claude channel, switch Codex Desktop to managed app-server, or make
tmux wake a default. No token, account data, agent UUID, message body, or private local path is
included in this record.
