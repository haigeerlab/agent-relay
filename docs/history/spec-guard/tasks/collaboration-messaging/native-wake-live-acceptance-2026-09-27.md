# Native live-host acceptance — 2026-09-27

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **controlled same-Mac Claude Code ↔ Codex trial passed; native remains experimental and
is selected on this host, not automatically for all installations**.

The operator separately authorized this retry after the earlier trial had been rolled back.
Before activation, the eight historical XATS identities were reviewed as ended; the three
historical unread deliveries were retained, not acknowledged or discarded. XATS was stopped but
its LaunchAgent file and mailbox were preserved. A consistent private archive passed integrity,
inventory, logical-content and SHA-256 checks before the operator-only activation wrote the
native selector. The pinned runtime was commit
`8f12c880cfdba73812b6ab7bc0f373fc467e0343`.

## Ordinary host journey

- A fresh Codex Desktop task and a fresh Claude Code CLI session joined through the installed
  `collab` entry, each binding its own session without a user-supplied ID. Claude started with
  `--chrome`; both sessions discovered the other through the native mailbox.
- Claude sent direct test message **5** to idle Codex. Codex entered a new turn, read and
  acknowledged it, then replied with direct message **6**. Idle Claude entered a new turn, read
  and acknowledged the reply. Both test inboxes ended with zero unacknowledged deliveries. Mailbox
  write and wake receipt alone were not counted as reading; the read and acknowledgement were
  observed separately. No human copied the message between hosts.
- Claude Code in Chrome opened and inspected an isolated public test page, then closed its test
  tab. ChatGPT in Chrome independently opened and inspected an isolated public test page through
  its existing browser connection, then closed its test tab. Neither integration was removed or
  reconfigured for collaboration.

After the test, the two exact temporary native identities were retired without closing backlog
or notifying senders. The native mailbox retained its six test messages and had zero registered
identities and zero unacknowledged deliveries. The XATS archive checksum and its eight identities
and three unread deliveries stayed unchanged. A read-only follow-up reported selector `native`
and pinned runtime `ready`; XATS remained stopped. No repository code, Git state, release,
browser configuration or message body was changed by this acceptance.

## Independent-project follow-up

A later test used a Claude Code CLI session in an independent validation Git repository, not a
linked worktree of this source repository. The existing Codex Desktop task joined from this
source repository. Claude used the installed `collab` entry; Codex used its native communication
tools under the same contract. Both saw selector `native` and registered temporary, self-bound
identities. Claude discovered Codex by name, then sent direct
message **7** across the project boundary. Codex read and acknowledged **7**, then sent reply
**8**. Claude resumed the same conversation, read and acknowledged **8**. Both inboxes ended with
zero unread messages, and the sender's outbox recorded an acknowledgement timestamp for **8**.
No message was relayed by a person or used as authorization to change project state.

The first CLI attempt used a `dontAsk` test permission mode that denied even the backend check
and messaging tools, so it registered no identity and sent nothing. The retry explicitly allowed
only that check and the native communication tools; it did not grant file or Git writes. Because
the one-shot CLI process had exited when Codex replied, wake reported `pending/offline` while
**8** remained in the mailbox. Resuming the same Claude conversation recovered and acknowledged
it. This demonstrates durable delivery after an offline recipient, **not** an idle wake of a
running Claude process. The bridge's descriptive wake detail could lag the acknowledgement;
the outbox's `acknowledgedAt` was used as the handling evidence.

Both exact temporary identities were retired with backlog and notices disabled only after their
unread counts reached zero. Retirement unbound both sessions, closed no messages and sent no
notices; the message history was retained. The native agent list then showed zero active agents.
Both repositories' Git file status remained unchanged, and the host still selected native.

## Boundary of this result

Together these trials prove same- and different-project conversations on one Mac, bidirectional
idle wake for live sessions in the first trial, and both functional Chrome integrations at the
tested host versions. They do not cover every busy/offline/permission-held path, compatibility
after future host updates, or a general release for other users. The native wake path depends on
observed private host IPC; unread mail remains the fallback if wake is unavailable. Old XATS
history and the guarded rollback remain available, but no rollback was performed after the
successful trial.
