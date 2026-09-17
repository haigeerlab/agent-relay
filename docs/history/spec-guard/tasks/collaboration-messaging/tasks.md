# Task list: collaboration-messaging

Plan: [`plan.md`](plan.md)
Local Proposal candidate: [`../../spec/proposals/collaboration-messaging.md`](../../spec/proposals/collaboration-messaging.md)

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
**Status:** Pending — deliberately not started.

**Acceptance criteria:**

- [ ] A human explicitly authorizes any commit, publication, and tracker action.
- [ ] The candidate is independently reviewed and accepted through the existing workflow before any Capability Map change.

**Verification:**

- [ ] Fresh remote-main facts and the workflow's read-only preflight support the requested promotion.
