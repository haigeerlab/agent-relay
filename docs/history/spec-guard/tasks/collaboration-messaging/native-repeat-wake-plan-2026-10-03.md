# Plan: same-Mac repeat-wake reliability

Module: [`../../spec/collaboration-messaging.md`](../../spec/collaboration-messaging.md)

Status: implemented and verified on one ordinary same-Mac Claude Code target; general native
promotion remains gated separately.

## Goal

Let a user name a local session, its host (`Claude Code` or `Codex`) and project in one sentence.
The current agent resolves one unique registered identity, sends the message and, when that target
has explicitly bound wake and is still running, wakes it repeatedly without asking the user to type
a seed message in the target window.

## Contract

1. A target session owns its registration and wake opt-in. A sender can request a ping but cannot
   bind another conversation or change its permission mode.
2. Name, host and project are discovery hints, not a project group or access-control rule. Zero
   matches stop with one setup instruction; ambiguous matches ask for the smallest distinction.
3. Consecutive messages reuse the original sender identity, recipient identity, thread and wake
   binding. They do not re-register or unbind either side.
4. Mailbox write, immediate wake receipt, read and acknowledgement remain separate. An immediate
   `unknown` receipt is inconclusive; later read or acknowledgement can establish actual pickup.
5. A stopped process or unbound target remains mailbox-only. Starting applications, changing
   global configuration, cross-machine networking and forced wake are out of scope.

## Implementation slices

1. Add failing source-contract tests for one-sentence targeting, unbound-recipient handling and
   repeat-wake evidence.
2. Tighten the existing `collab` skill instructions without adding a resolver database, project
   topology or new transport behavior.
3. Run two consecutive real-host wake cycles against one persistent Claude Code session and record
   sanitized evidence.
4. Run focused and repository validation, then submit the change on an independent branch.

## Acceptance

- Two consecutive direct messages cause two new turns in the same idle, explicitly bound target.
- Each turn reads, replies on the original thread and acknowledges the original message.
- No human types in the target between the two sends.
- Both test inboxes end with zero unread messages; old identities and their mail are untouched.
- Failure wording distinguishes unbound, stopped, held, unknown, read and acknowledged states.

The executed evidence is in
[`native-repeat-wake-acceptance-2026-10-03.md`](native-repeat-wake-acceptance-2026-10-03.md).
