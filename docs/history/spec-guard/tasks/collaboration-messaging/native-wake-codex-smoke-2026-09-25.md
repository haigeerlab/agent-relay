# Native Codex wake smoke — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **two-task Codex exchange passed; Tasks 1 and 2 remain pending**. This was an isolated test of
the pinned `claude-codex-mcp-bridge` commit `8f12c880cfdba73812b6ab7bc0f373fc467e0343` on
ordinary Codex Desktop. The existing XATS mailbox, service and host entry were not changed.

## Observed

- After a Desktop restart, the current task's actual callable catalog contained exactly ten
  `spec_guard_wake_trial` communication tools: register, send, sessions, wake status, inbox, wait,
  acknowledge, thread, agents and outbox. Worker, review and orchestration functions were absent
  from the callable catalog. Codex parsed the configured `enabled_tools` list. Upstream MCP server
  instructions still mentioned worker operations, so host filtering is a callable-tool boundary,
  not a clean mailbox-only upstream description.
- `bridge_sessions` returned `thisSession: null`; the MCP process did not identify the calling
  Codex task automatically. The Agent's command environment supplied an exact current task ID,
  independently matched to the Desktop task listing. That ID was passed internally to bind only
  this task in the isolated mailbox; no ID was requested from the user or stored in this record.
- A synthetic direct test message, ID **1**, was committed to the isolated mailbox while this
  task was busy. The wake job first reported `pending` with reason `busy`. After this task ended
  its turn, the bridge reported `accepted` with `Codex confirmed a new turn`, and this task
  actually received the background notification. It read message ID 1 from its inbox and
  acknowledged it; the unread count became zero. The synthetic sender was intentionally
  unregistered, so no reply was sent to it.
- After acknowledgement, `bridge_outbox` reported zero unacknowledged messages and an
  `acknowledgedAt` timestamp. However, the wake receipt still had state `read` and its detail
  still said work was not acknowledged. The integration must use the separate acknowledgement
  field, not that stale wake-detail sentence, when reporting handling status.
- A second same-project Desktop task existed throughout. Its last recorded turn did not advance
  after the test send, consistent with the ping targeting only the bound task. Attempts to ask
  that separate task for its loaded tool catalog produced empty completed turns, so its own
  bridge connection and two-way messaging were **not** verified in that first run.
- A fresh second same-project Desktop worktree task later checked its own callable catalog: the
  same ten communication tools were present, with no worker, review or orchestration tools. It
  obtained its own `CODEX_THREAD_ID` from its command environment and registered only itself in
  the isolated mailbox. Its binding matched its actual Desktop task ID; this task did not register
  or impersonate it.
- With that second task idle, this task sent direct message **2** to its registered name. The
  bridge reported `accepted` and `Codex confirmed a new turn`. The target completed a new turn,
  read message 2, acknowledged only message 2, and sent result message **3** back. This task read
  and acknowledged message 3; both inboxes then had zero unread messages. The target's completed
  turn and its mailbox operations were independently visible in the Desktop task record. Neither
  task changed code, Git, configuration or the existing XATS mailbox during this exchange.

## Not yet established

- Fresh Claude Code registration, fork behavior, busy/permission-held/absent targets, and both
  Chrome integrations remain untested in this run. Two accepted Codex wakes and one two-way
  exchange are not proof of the complete daily workflow.
- The trial's temporary MCP entry, private runtime and isolated mailbox remain only for the
  controlled follow-up; they must be removed after acceptance or an explicit no-go decision.
  No production cutover is authorized by this record. XATS remains the daily default.
