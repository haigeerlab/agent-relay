# Claude Code CLI tmux wake acceptance

Status: **passed on the tested same-Mac Claude Code CLI path**. Native Codex Desktop remains
mailbox-only; this does not claim active wake for every host or session.

## Verified

- A controlled interactive launch through `--tmux-wake` entered a new tmux session and exited
  cleanly with a harmless fake Claude executable. The temporary private runtime was removed.
- A real Claude Code CLI session started in a tmux pane and loaded the installed `collab` skill.
  It self-registered using its own session identity, read an empty inbox, and later unregistered
  itself before the test session exited.
- The existing XATS service was `service-running` in a host-side check. A sandbox-only health or
  service-status check falsely reported it offline, so that result was not used to restart it.
- The first real registration reported `spawn tmux ENOENT` because the installed LaunchAgent PATH
  omitted tmux. That attempt was mailbox-only and did not receive a test message.
- With the user's explicit approval, the managed LaunchAgent was refreshed. Its PATH now includes
  the installed tmux directory; host-side service status and runtime health were both running.
- A new real Claude Code CLI session self-registered and reported binding to tmux pane `%0`. It
  completed its first turn and was idle before the peer sent one benign message.
- The peer's send wrote one mailbox event and reported `poked: true`, with no skip reason. The
  recipient's own `get_inbox` read that message after about 3 seconds, and it replied with the
  agreed acknowledgement. The peer then read the reply. The CLI output independently showed the
  short wake hint arriving without a manual prompt.
- Both temporary test identities were unregistered and the temporary Claude CLI session exited.

No message body, token, PID, or full local path is included in this record. Mailbox acceptance,
successful poke, recipient read, and reply are separate observed facts.

Native Codex Desktop was not reconfigured; its mailbox mode and ChatGPT in Chrome remain unchanged.
