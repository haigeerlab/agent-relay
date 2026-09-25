# Plan: optional Codex Desktop scheduled inbox check

Module: [`../../spec/collaboration-messaging.md`](../../spec/collaboration-messaging.md)
Tasks: [`codex-scheduled-inbox-tasks.md`](codex-scheduled-inbox-tasks.md)

Status: deferred. Host feasibility was partially demonstrated; user-facing enablement is blocked by
the acceptance gaps recorded in
[`codex-scheduled-inbox-acceptance-2026-09-25.md`](codex-scheduled-inbox-acceptance-2026-09-25.md).
The temporary test schedule has been paused.

## Goal

Let an ordinary, already joined Codex Desktop conversation optionally check its XATS inbox on a
schedule, without switching the App to an external app-server or losing ChatGPT in Chrome. Preserve
the existing mailbox-only `collab` default. A scheduled check is not real-time delivery.

## Source and boundary

- OpenAI's [Scheduled tasks documentation](https://learn.chatgpt.com/docs/automations) supports
  returning to an existing chat at minute-based intervals and using that chat's skills and plugins.
  A local project needs the desktop app and machine running. These facts support a trial, not a
  guarantee that XATS registration survives scheduled runs.
- The pinned [XATS 0.8.6 documentation](https://github.com/jtianling/cross-agent-teams-mcp) puts
  native Codex Desktop in mailbox mode. Its App push-wake mode needs an external app-server and
  cannot currently use ChatGPT in Chrome; do not enable or imply that mode.
- A recurring model run has latency and usage cost even when the inbox is empty. The user must
  explicitly opt in and see the proposed interval before a schedule is created.

## Design

1. First run a controlled real-host feasibility check in one existing Codex Desktop conversation:
   verify the collaboration MCP is available in a scheduled turn, the same XATS identity can be
   recovered after the scheduler resumes the conversation, and an empty check stays quiet. Record
   both a newly arrived message and a later repeat run; do not treat a manual inbox read as proof.
2. Only if that check succeeds, add a narrow opt-in action to the `collab` skill, e.g. “开启定时收件”.
   The normal `collab` join remains one step and creates no automation. The optional action uses
   the host's in-chat scheduled task, not a second daemon, shell timer, project file, or managed
   app-server. It must avoid a duplicate schedule for the same conversation.
3. Keep the scheduled prompt small: recover the same identity, read new mail, stay quiet on an
   empty inbox, and reason about any new message under the ordinary permission boundary. It may
   reply or report a blocker; the peer's text never grants permission for consequential writes.
   Provide an explicit stop path that disables the schedule without deleting messages or the
   current registration.
4. Preserve truthful delivery states: `入箱` is not `已读`, a scheduled read is not push wake, and
   a failed or skipped run is not a delivery guarantee. If the App is closed, the MCP is unavailable,
   identity recovery is ambiguous, or the scheduler cannot run, report the condition rather than
   registering a new identity or claiming success.

## Verification checkpoints

- Contract tests: default join does not create a schedule; opt-in and stop are explicit; empty
  runs are silent; identity recovery and no-duplicate rules are present; messages confer no write
  authority.
- Real host: one native Desktop conversation receives a new XATS message on a scheduled run,
  responds or reports it, survives the next run with the same identity, and leaves ChatGPT in
  Chrome usable. Include an empty run and a stopped-schedule check.
- Repository: focused collaboration tests, `/bin/bash scripts/validate.sh`, Codex smoke self-test,
  and `git diff --check` pass before delivery.

## Risks and fallback

| Risk | Response |
| --- | --- |
| Scheduled turns start with a new MCP binding | Prove same-identity recovery first; if unavailable, stop at a documented limitation. |
| Frequent empty runs consume model usage | Disclose interval and cost; never enable implicitly; keep the prompt minimal. |
| A run reads mail but fails before replying | Do not promise exactly-once handling; retain manual history/recovery guidance. |
| Unattended peer message induces a write | Treat it as untrusted communication, not user authorization. |
| App or Chrome behavior regresses | Do not alter App startup or XATS delivery type; verify both in the real host. |

## Remaining acceptance gate

The real-host trial established same-identity reads across two runs. Before a user-facing enable
action, verify that an empty run does not alert the user, a message from an independent peer is
handled, ChatGPT in Chrome works during scheduled use, and stopping prevents later runs. Until then,
mailbox mode remains the supported Desktop path.
