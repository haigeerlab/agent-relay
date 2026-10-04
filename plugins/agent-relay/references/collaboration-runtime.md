# Native collaboration runtime

Spec Guard uses one private same-Mac bridge for Claude Code ↔ Codex communication. Same-host communication still
prefers each host's built-in session tools. The bridge is not a network service, tracker, job queue, or authority
channel.

## Private data

The default root is `~/.spec-guard/native-collaboration/`. It is user-global rather than project-local, so sessions
from different projects on the same Mac can discover one another after they explicitly join. A fresh plugin
installation contains no user data and does not create this directory until explicit runtime installation.

Expected contents include the pinned server bundle and manifest, an owner-private SQLite mailbox and backups, and
runtime data. Project repositories never contain mailbox data or secrets.

## Read-only status

From the installed plugin root:

```bash
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py status
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py probe
```

Status verifies the pinned revision, expected files, ownership, permissions, and runtime shape. Probe checks the
server without registering an identity or reading message bodies. An invalid or unavailable result is a stop
condition, not permission to substitute another implementation.

## Explicit installation

After the user approves creating the private runtime:

```bash
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py install
```

The install command uses the repository-pinned upstream revision. It does not modify Claude or Codex config.

## Host attachment

Inspect exact generated fragments first:

```bash
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py claude
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py codex
```

After separate explicit approval:

```bash
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py install-claude
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py install-codex
```

Claude registration uses its supported user MCP CLI. Codex appends only the exact managed table and refuses an
existing or ambiguous table. Neither command accepts project trust, project MCP approval, or broader permissions
for the user. Existing sessions normally need a restart to load a new entry.

Removal also requires explicit approval:

```bash
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py \
  uninstall-claude --confirm-uninstall
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py \
  uninstall-codex --confirm-uninstall
```

Only an exact managed entry is removed. Edited Codex configuration fails closed with manual guidance. Mailbox
history and runtime files remain.

## Session registration and wake

Daily use begins with a lazy `bridge_register`. The visible name contains a human-readable prefix and a short
opaque suffix. The same session reuses its first successful identity.

Default registration sets `wake: null`. Explicit wake binding is allowed only for the current trusted session and
only after the user requests it. Claude uses verified `thisSession`; Codex uses the current task's trusted
`CODEX_THREAD_ID`. Full-auto or bypass sessions must not bind wake.

Wake is best effort and separate from delivery. A message can remain safely queued when wake is unavailable or
held. Use `bridge_wake_status` for wake facts and `bridge_outbox` for acknowledgement; do not infer either from a
registered row or recent activity.

## Identity retirement

After a session has ended, read its inbox and acknowledge actually processed messages. Then, with user approval:

```bash
python3 -B plugins/spec-guard/hooks/native_collaboration_retire.py \
  --name '<exact-name>' --confirm-retire
```

The command verifies the pinned runtime, requires an exact name, refuses any unacknowledged direct or broadcast
delivery, and retires the identity while keeping backlog. It does not delete the database.

## Claude project permissions

Claude project trust, first MCP approval, and `.claude/settings.json` allow rules are independent. For smooth
authorized work, the user may preconfigure only the exact `mcp__spec-guard-native-collaboration__bridge_*` tools
needed by the workflow. Review requires no extra edit tools; bounded development additionally needs explicit Edit,
Write, and task-scoped Bash permission. Spec Guard diagnoses missing rules but never writes them without a separate
request and never recommends bypass mode.

## Troubleshooting order

1. Confirm the installed plugin root and run runtime `status`.
2. Verify the current host actually loaded the native MCP entry; an already-running session may need restart.
3. Confirm the target appears exactly once in `bridge_agents` and has the intended wake binding.
4. For an unknown send, inspect the original outbox and wake status; do not resend.
5. For Claude held states, distinguish project trust, MCP approval, allow rules, and target busy state.
6. For Codex, use the App-managed supported binary; do not use an older PATH binary or add a model override.

Never scan unrelated real mailbox messages during diagnosis. Read only the exact identities or message IDs the
user placed in scope. Do not expose this runtime to another machine.
