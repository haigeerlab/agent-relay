# Native collaboration runtime

agent-relay uses one private same-Mac bridge for Claude Code ↔ Codex communication. Same-host communication still
prefers each host's built-in session tools. The bridge is not a network service, tracker, job queue, or authority
channel.

## Private data

The default root is `~/.agent-relay/runtime/`. It is user-global rather than project-local, so sessions
from different projects on the same Mac can discover one another after they explicitly join. A fresh plugin
installation contains no user data and does not create this directory until explicit runtime installation.

Expected contents include the pinned server bundle and manifest, an owner-private SQLite mailbox and backups, and
runtime data. Project repositories never contain mailbox data or secrets.

## Read-only status

From the installed plugin root (`$ROOT`, resolved as in the `collaboration-ops` skill):

```bash
python3 -B "$ROOT/hooks/native_collaboration_runtime.py" status
python3 -B "$ROOT/hooks/native_collaboration_runtime.py" probe
```

Status verifies the pinned revision, expected files, ownership, permissions, and runtime shape. Probe checks the
server without registering an identity or reading message bodies. An invalid or unavailable result is a stop
condition, not permission to substitute another implementation.

## Explicit installation

After the user approves creating the private runtime:

```bash
python3 -B "$ROOT/hooks/native_collaboration_runtime.py" install
```

The install command builds from the bridge copy shipped in the plugin (`bridge/`, checked file by file against
`bridge/UPSTREAM.sha256`); it needs no git, but `npm ci` still needs network. It does not modify Claude or Codex config.

The delegation controller, `doctor`, the runtime's `install`/`upgrade`, identity retirement and the host adapters
(`install-claude`/`install-codex` and the printed configuration) use the node pinned in the host entries (order:
`--node` → Claude entry → Codex entry → PATH), not the current shell's PATH; npm runs on that node during install,
and `--npm` defaults to the npm beside it. A selected node below 22.5.0 is refused (`node-too-old`) before any host
is touched or any build starts.

## Host attachment

Inspect exact generated fragments first:

```bash
python3 -B "$ROOT/hooks/native_collaboration_adapters.py" claude
python3 -B "$ROOT/hooks/native_collaboration_adapters.py" codex
```

After separate explicit approval:

```bash
python3 -B "$ROOT/hooks/native_collaboration_adapters.py" install-claude
python3 -B "$ROOT/hooks/native_collaboration_adapters.py" install-codex
```

Claude registration uses its supported user MCP CLI. Codex appends only the exact managed table and refuses an
existing or ambiguous table. Neither command accepts project trust, project MCP approval, or broader permissions
for the user. Existing sessions normally need a restart to load a new entry.

Removal also requires explicit approval:

```bash
python3 -B "$ROOT/hooks/native_collaboration_adapters.py" \
  uninstall-claude --confirm-uninstall
python3 -B "$ROOT/hooks/native_collaboration_adapters.py" \
  uninstall-codex --confirm-uninstall
```

Only an exact managed entry is removed. Edited Codex configuration fails closed with manual guidance. Mailbox
history and runtime files remain.

## Session registration and wake

Daily use begins with a lazy `bridge_register`. The visible name contains a human-readable prefix and a short
opaque suffix. The same session reuses its first successful identity.

Default registration sets `wake: null`. Explicit wake binding is allowed only for the current trusted session and
only after the user requests it. Claude uses verified `thisSession`; Codex uses the current task's trusted
`CODEX_THREAD_ID`. Any permission mode may bind wake (`wake-any-mode`): a woken turn runs under that session's own
settings, which the bridge never changes or approves. A Claude session in Bypass permissions holds cross-session
pings until they expire, so binding there does not wake it (bridge `docs/BACKGROUND-WAKE.md`, "Why Claude pings
expire"); tell the user, never change the setting for them.

Wake is best effort and separate from delivery. A message can remain safely queued when wake is unavailable or
held. Use `bridge_wake_status` for wake facts and `bridge_outbox` for acknowledgement; do not infer either from a
registered row or recent activity.

## Health check, upgrade and recovery

`doctor` is the read-only health check (runtime, probe, mailbox, host entries, plugin copies, notifications, wake
bindings, Codex restart after an upgrade); every `warn` or `fail` carries its next step.

```bash
python3 -B "$ROOT/hooks/native_collaboration_runtime.py" doctor
```

When `status` reports `bridge.current: false`, the plugin carries a newer bridge. With the user's agreement and every
session that uses the mailbox closed, `upgrade --confirm` backs the mailbox up, builds beside the old runtime, swaps,
and rolls back on failure; `rollback --confirm` returns to the newest `runtime.previous-*`; an interrupted swap shows
as `interrupted` and is put back with `recover --confirm`. The `collaboration-ops` skill and the README section
"升级运行时" give the exact steps. None of these delete old directories; the user does.

## Identity retirement

After a session has ended, read its inbox and acknowledge actually processed messages. Then, with user approval:

```bash
python3 -B "$ROOT/hooks/native_collaboration_retire.py" \
  --name '<exact-name>' --confirm-retire
```

The command verifies the pinned runtime, requires an exact name, refuses any unacknowledged direct or broadcast
delivery (an expired message does not count; the refusal lists up to ten blocking message ids with their delivery
state, never their text), and retires the identity while keeping backlog. It does not delete the database.

A retired name stays retired: `bridge_register` refuses it, with or without `takeover`, unless the call passes
`reactivate: true`, which needs the user's agreement; the result then says `reactivated: true`. A Codex delegation
whose identity was retired holds its follow-ups with `identity-retired`.

## Claude project permissions

Claude project trust, first MCP approval, and `.claude/settings.json` allow rules are independent. For smooth
authorized work, the user may preconfigure only the exact `mcp__agent-relay__bridge_*` tools
needed by the workflow. Review requires no extra edit tools; bounded development additionally needs explicit Edit,
Write, and task-scoped Bash permission. agent-relay diagnoses missing rules but never writes them without a separate
request and never recommends bypass mode.

## Troubleshooting order

1. Confirm the installed plugin root and run runtime `status`.
2. Verify the current host actually loaded the native MCP entry; an already-running session may need restart.
3. Confirm the target appears exactly once in `bridge_agents` and has the intended wake binding.
4. For an unknown send, inspect the original outbox and wake status; do not resend.
5. For Claude held states, distinguish project trust, MCP approval, allow rules, and target busy state.
6. For Codex, use the App-managed supported binary; do not use an older PATH binary or add a model override.
7. A Codex identity with `presence: not-loaded` belongs to a task the ChatGPT app has not opened since it started:
   the user opens it there and the message is delivered. It is not a connection or identity fault.
8. A send or ack refused because the name is not registered by this session (after a bridge restart; for Codex also
   after the ChatGPT app restarts or a long-idle task is reopened) is fixed by registering the same name again, Codex
   passing its own `CODEX_THREAD_ID`; no takeover is needed.

Never scan unrelated real mailbox messages during diagnosis. Read only the exact identities or message IDs the
user placed in scope. Do not expose this runtime to another machine.
