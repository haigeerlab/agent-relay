# Task list: collaboration-messaging

Plan: [`plan.md`](plan.md)
Proposal: [`../../spec/proposals/collaboration-messaging.md`](../../spec/proposals/collaboration-messaging.md)

This is a local implementation checklist. It does not replace the Proposal tracker lifecycle and does
not authorize remote writes.

## Task 1: Establish the private same-Mac runtime

**Dependencies:** None.
**Status:** Complete.

**Acceptance criteria:**

- [x] Fixed XATS version runs only on loopback with a private user token.
- [x] Explicit launchd lifecycle does not expose token material in plist, argv, or logs.
- [x] Invalid permissions and unrecognised managed-service files are rejected.

**Verification:**

- [x] Focused runtime fixtures pass.
- [x] Host verification confirms `127.0.0.1:9100` is the only listening address.

## Task 2: Connect Claude Code and native Codex Desktop

**Dependencies:** Task 1.
**Status:** Complete.

**Acceptance criteria:**

- [x] Claude user-level configuration and Codex header helper contain no token.
- [x] Both hosts can register, send, read, and acknowledge persistent messages.
- [x] Native Codex Desktop stays mailbox-only, preserving ChatGPT in Chrome.

**Verification:**

- [x] A continuous normal Claude Code session and native Codex Desktop completed a real two-way mailbox exchange.
- [x] Adapter and runtime test suites pass.

## Task 3: Provide safe operator controls and recovery boundaries

**Dependencies:** Tasks 1–2.
**Status:** Complete.

**Acceptance criteria:**

- [x] Commands and skill documentation distinguish inspect, explicit enable, and explicit cleanup.
- [x] Registry cleanup accepts only a user-supplied UUID and cannot terminate a process or delete messages.
- [x] Project paths and roles remain display-only self-description, never routing or ownership rules.

**Verification:**

- [x] `./scripts/validate.sh` passes.
- [x] Proposal contract validation and `git diff --check` pass.

## Checkpoint: Local implementation ready for review

- [x] No Git/Issue/Ticket write path was added.
- [x] Capability Map remains unchanged.
- [x] Full repository validation passes.

## Task 4: Publish and evaluate the Proposal candidate

**Dependencies:** Human direction and the repository's explicit Proposal workflow.
**Status:** Complete — independently accepted, promoted, and proved on the remote default branch.

**Acceptance criteria:**

- [x] A human explicitly authorized local commits and publication to `origin/main`.
- [x] The candidate was independently reviewed and accepted before the Capability Map change.

**Verification:**

- [x] The candidate is present on `origin/main` as commit `e495f9f`.
- [x] Fresh preflight returned `ready`, and post-merge proof returned `proved` for promotion commit
  `d05b8cff6d8edcd9ba1bd3388a452ee18b5507bf`.

## Task 5: Provide the one-step `collab` entry

**Dependencies:** Tasks 1–3.
**Status:** Complete — source contracts, focused tests, host discovery, and unavailable-endpoint
diagnostics pass.

**Description:** Add a daily-use `collab` skill whose only public concern is joining the local
conversation, reading the inbox, discovering peers, and sending a user-directed message. Keep the
existing `collaboration-ops` skill and command as explicit operator controls; do not turn start,
configuration, cleanup, or app-server wake into side effects of the daily entry.

**Acceptance criteria:**

- [x] A new Claude Code or Codex session can invoke `collab`, optionally with one friendly alias,
  without supplying project path, team, PID, agent type, or raw MCP tool names.
- [x] The entry performs only a status check until an available runtime makes same-session lazy
  registration safe; unavailable states give one precise next action and make no configuration,
  service, Git, Issue, or Ticket write.
- [x] The Claude-compatible slash surface and Codex skill surface are both verified rather than
  merely documented.

**Verification:**

- [x] Focused contracts cover enabled, absent, offline, already-registered, and process-local
  endpoint failure states.
- [x] Real Claude Code and native Codex Desktop each expose a discoverable `collab` entry after a
  normal restart.

## Task 6: Hide transport identity and let the Agent resolve human names

**Dependencies:** Task 5.
**Status:** Complete — unique, missing, and ambiguous cases pass without a matcher or routing
framework.

**Description:** Keep transport identity unique while leaving human-name understanding to the
Agent. A friendly alias is optional; the transport name always contains a generated per-session
suffix. The Agent reads visible, voluntary self-description facts and sends only on one unique
match. Do not add a fixed matching helper, alias database, project topology, or routing rules.

**Acceptance criteria:**

- [x] A missing alias yields a readable automatic display identity; a friendly alias remains
  discoverable while the underlying registration cannot collide with an older session.
- [x] A natural-language recipient request lists candidates internally and sends only when one
  candidate matches.
- [x] Zero matches explain that the intended session must first join; multiple matches request one
  concise distinction and never choose a recipient silently.

**Verification:**

- [x] Focused tests cover generated identity uniqueness, alias/project/host matching, no match,
  and ambiguity.
- [x] Tests prove no matcher creates project groups, role routing, assignments, or access
  restrictions.
- [x] Real-host edge checks leave the mailbox unchanged for zero and ambiguous matches.

## Task 7: Accept the user-facing Claude↔Codex flow

**Dependencies:** Tasks 5–6.
**Status:** Complete — real Claude Code, Codex CLI, and native Codex Desktop completed same-project
and different-project mailbox exchange while preserving ChatGPT in Chrome.

**Acceptance criteria:**

- [x] Claude and Codex can join with human-readable identities, discover one another, and exchange
  a reply without manual transport fields.
- [x] Same-project and different-project examples work without project-group setup.
- [x] Native Codex Desktop retains ChatGPT in Chrome, and delivery remains described as mailbox
  acceptance rather than guaranteed real-time wake-up.

**Verification:**

- [x] Focused collaboration suites, repository validation, and Codex smoke self-test pass.
- [x] The acceptance record contains only non-secret host and message metadata.

## Checkpoint: Collaboration messaging ready for delivery review

- [x] A newcomer needs at most `collab [optional alias]` to become findable.
- [x] A sender can address a peer by human name or visible description, with ambiguity handled
  explicitly.
- [x] No project grouping, auto-start, Git write, token exposure, or Codex app-server change was
  introduced.
- [x] Capability Map, Proposal, and acceptance attestation remain unchanged in this delivery.
