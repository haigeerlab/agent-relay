# Native Desktop idle-wake trial — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **Codex idle wake passed in an isolated mailbox; ordinary `collab` entry is not yet proven.**
This trial used pinned MIT upstream `claude-codex-mcp-bridge` commit
`8f12c880cfdba73812b6ab7bc0f373fc467e0343`. XATS remained the supported mailbox.

## Evidence

- A temporary user-level MCP entry allowed exactly eight communication tools. After the user
  restarted Codex Desktop, those eight tools appeared in this task's callable catalog; upstream
  worker, review and orchestration tools did not. The pinned build and all 70 upstream tests
  passed on the real host. The earlier sandbox-only process/socket `EPERM` was not counted as an
  upstream failure.
- `bridge_sessions.thisSession` and `codexSessionId` were both `null`. The Agent read its own
  `CODEX_THREAD_ID` from the current task environment and bound a unique temporary name to that
  exact Codex task. No task ID came from the user. This still required internal manual registration,
  so it does **not** satisfy the normal one-command `collab` criterion.
- A separate local MCP client registered a synthetic sender. Silent message **1** reached the
  Desktop task's inbox and was acknowledged; unread became zero.
- The sender then scheduled direct message **2** for after the current turn ended, with wake
  enabled. The bridge returned `accepted` and `Codex confirmed a new turn`. Codex actually resumed
  this task from idle, read message 2, and acknowledged it. Sender outbox reported
  `totalUnacknowledged: 0` with an `acknowledgedAt` timestamp. No code, Git, XATS mailbox or
  Chrome setting was changed by the exchange.
- The wake receipt's state advanced to `read`, but its detail still said the work was not
  acknowledged despite `acknowledgedAt`. An adapter must derive handling from the acknowledgement
  field, not that stale sentence.

## Cleanup and remaining gates

The temporary MCP stanza was removed; the user config matched its pretrial backup exactly, and
`codex mcp get` no longer found the trial server. Four processes running only the trial server
were terminated, and the owner-private temporary checkout and test mailbox were deleted. The
repository remained clean. The current task may retain a stale tool catalog until another app
restart, but the trial server is no longer configured or running.

This run did not test Claude Code, direct rejection of a disallowed worker-tool call, or the
ordinary `collab` skill. It supports the Codex idle-wake mechanism and narrow Codex host catalog;
Task 1 also depends on the earlier two-task, Claude and failure-case records. This run alone does
not establish Task 2, a go decision, or product cutover.
