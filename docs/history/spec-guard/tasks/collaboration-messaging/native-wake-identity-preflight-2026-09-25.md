# Native wake identity preflight — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **partial evidence, Task 1 not passed**. This was a read-only check in the current ordinary
Codex Desktop task. No bridge runtime, service, host configuration, new task, or message was created.
No raw task ID is stored in this record.

## Observed

- The current command-tool environment contains `CODEX_THREAD_ID` and `CODEX_SESSION_ID`. In this
  root task, both values matched the current task ID returned by the desktop task listing. The
  comparison returned only yes/no, not the identifier.
- The desktop task listing exposed task IDs but no explicit `currentTaskId` field. Selecting the
  sole active task by title, project path, or recency is not an acceptable binding method.
- The earlier isolated bridge trial needed an explicit Codex task ID because its MCP-side
  `bridge_sessions` returned no current-session identity. A command-tool environment variable is
  therefore a **candidate Agent-side input** to `bridge_register`, not proof that the bridge MCP
  process can discover its caller automatically.

## Contract and limits

OpenAI Docs describes a `session_id` field on Codex hooks, but the
[app-server contract](https://learn.chatgpt.com/docs/app-server) distinguishes a thread ID from the session-tree root:
forked threads have their own thread ID and retain the root's session ID. Hook `session_id` must not
be assumed to identify the exact wake target in a fork. The current `CODEX_THREAD_ID` environment
variable is observed on this host but is not established by the reviewed public documentation as
a stable cross-host MCP contract.

The next isolated test must verify that `collab` can read an exact ID from **its own** task context,
pass it to the bridge without user input, and wake only the addressed task when two same-project
tasks (including a fork if available) are open. An absent or mismatched ID must leave the session
mailbox-only; it must never guess by title, project, status, or most-recent activity. This test
needs a separate task and a temporary bridge connection, neither of which was created here.

Sources: [Codex hook input fields](https://learn.chatgpt.com/docs/hooks),
[Codex app-server thread/session distinction](https://learn.chatgpt.com/docs/app-server),
[bridge wake binding guide](https://github.com/WebisityStudio/claude-codex-mcp-bridge/blob/main/docs/BACKGROUND-WAKE.md).

## Follow-up: two ordinary Desktop tasks

A separate same-project Codex Desktop task was then created in a managed worktree for a read-only
identity check. In that task, both `CODEX_THREAD_ID` and `CODEX_SESSION_ID` matched the task ID
reported by the Desktop task listing. In this original task, both variables still matched this
task's own listed ID. The two IDs differed. This rejects a shared project/title identity for these
two root tasks without storing either raw ID in the repository.

The new task reported no temporary wake bridge, and `codex mcp get spec_guard_wake_trial`
confirmed that no such Codex configuration entry existed. It did not
register a collaboration identity, send a message, or change files, Git, configuration, or services.
Therefore this check proves only **exact root-task identity in each Agent command environment**;
it does not prove MCP-process access to the variable, fork semantics, bridge registration, idle
wake targeting, or the full Task 1 acceptance criteria. Keep XATS as the default.
