---
name: collaboration-ops
description: Inspect, explicitly initialize, or start Spec Guard's local Claude Code/Codex collaboration runtime.
---

# Collaboration operations

This is the operator surface for explicit setup, lifecycle, diagnosis, and cleanup. For daily use,
load the `collab` skill instead: it lets a session join, read messages, discover peers, and send by
human-readable name without exposing the fields below. 日常联调不得要求用户手工执行本页的注册细节。

Use this only for the optional same-Mac Agent messaging runtime. It provides a local directory and
free-text messages; it must not be reframed as project grouping, work assignment, Git control, or
a Ticket tracker.

XATS internally requires a `team` string. For every Spec Guard registration, pass the fixed value
`team: "spec-guard-local"`; do not derive it from the current directory and do not describe it to
the user as a project group. Its only job is to keep every same-Mac Spec Guard terminal in one
technical mailbox namespace. Set `project_dir` and free-text `role` independently as self-description;
they are display context, never a route, filter, or ownership lock.

Resolve the plugin root from the installed Spec Guard plugin and first run only:

```bash
python3 -B "$ROOT/hooks/collaboration_runtime.py" status --format json
```

If the status is `absent`, explain that initialization creates a private `~/.spec-guard/collaboration/`
directory, a `0600` token, and a fixed XATS runtime contract. Run `init` only after the user explicitly
asks to enable it. If the status is `valid`, run `start` only after the user explicitly asks to start the
local daemon, then use `health --format json`; report it as usable only if `daemon` is `running`.

Never place the token in a project file, MCP configuration, command argument, diagnosis, or response.
For Codex, use the generated `http_headers_helper` fragment. For Claude Code, the preferred explicit
one-time user setup is `python3 -B "$ROOT/hooks/collaboration_adapters.py" install-claude`; it configures
a no-secret stdio bridge for future normal Claude Code sessions. The temporary managed launcher remains a
diagnostic fallback. Read `references/collaboration-runtime.md` before giving host-specific instructions.

When registering a natively launched Codex Desktop session, use `agent_type="custom"` and
`agent_type_name="codex-desktop-native"`; it is mailbox-only. Do not claim or configure Codex push
wake unless the user explicitly accepts the separate managed app-server mode and its Desktop tradeoff.

If the user explicitly requests one-time Codex configuration, run
`python3 -B "$ROOT/hooks/collaboration_adapters.py" install-codex`. It appends only the no-secret
table to the Codex user config and refuses to overwrite an existing table; tell the user a Codex restart
is required. Do not run it merely because a runtime is valid.

For a Claude Code registration, pass `agent_type="claude-code"` and the current Claude parent process ID
as `ui_pid` when it is available (obtain it with `echo "$PPID"` in the Claude session). This lets XATS bind
the identity to a durable local runtime where supported; do not invent a pid. A short-lived `claude -p`
process that reconnects later is a different MCP connection and must use the supported recovery path rather
than assuming its prior tool-session identity survived.
