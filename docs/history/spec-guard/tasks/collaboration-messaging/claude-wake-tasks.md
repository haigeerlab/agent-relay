# Tasks: optional Claude Code channel wake

Plan: [`claude-wake-plan.md`](claude-wake-plan.md)

## Task 1: Verify the explicit launcher boundary

**Dependencies:** None.

**Description:** Cover the existing optional launcher with negative and positive contract tests,
then close only the option-override gaps those tests demonstrate.

**Acceptance criteria:**

- [x] Without `--enable-channel-wake`, no channel entry or channel flag is selected.
- [x] With explicit opt-in, the pinned channel entry and matching Claude flag are selected without
      putting the token in config or argv.
- [x] Caller arguments cannot override the selected MCP configuration or channel loader.

**Verification:** focused launcher tests failed before the fix and pass after it (27 tests).

**Files likely touched:** `plugins/spec-guard/hooks/collaboration_claude.py`,
`plugins/spec-guard/hooks/test_collaboration_runtime.py`.

**Estimated scope:** Small.

## Task 2: Resolve the safe opt-in path

**Dependencies:** Task 1.

**Description:** Do not expose the existing preview flag as a general-user enablement path while
Anthropic warns against using it with downloaded third-party channels. Document the boundary and
decide whether an applicable official approval route exists before revising the operator journey.

**Acceptance criteria:**

- [x] Operator guidance does not recommend the unsafe development-flag route to general users.
- [ ] An applicable official approval or separately accepted development-only path is identified
      before any exact active-wake enablement command is published.
- [ ] Guidance distinguishes CLI from Claude Desktop/editor sessions and states that preview,
      authentication, or organization policy can block wake without breaking mailbox delivery.
- [ ] No ordinary `collab` invocation installs, enables, or restarts a channel.

**Verification:** documentation contract tests pass; actual enablement remains unresolved.

**Files likely touched:** `plugins/spec-guard/skills/collaboration-ops/SKILL.md`,
`plugins/spec-guard/references/collaboration-runtime.md`,
`plugins/spec-guard/hooks/test_collab_entry.py`.

**Estimated scope:** Medium.

## Checkpoint: Safety boundary

- [x] Focused launcher and documentation tests pass.
- [x] Default Claude and native Codex behavior is unchanged.

## Task 3: Prove delivery on a real host

**Dependencies:** Tasks 1–2.

**Description:** Verify that the selected preview channel actually injects one benign message
into an idle CLI session, separating mailbox acceptance from observed wake.

**Acceptance criteria:**

- [ ] One idle, opt-in Claude Code CLI session receives a benign message without a manual inbox
      request and can reply. The current development-channel warning is recorded as **not passed**.
- [ ] A normal Claude session remains mailbox-only and Codex Desktop retains ChatGPT in Chrome.
- [ ] No token, full local path, or message body is copied into the acceptance record.

**Verification:** focused suites, full repository validation, Codex smoke self-test, and a
sanitized real-host acceptance note.

**Files likely touched:** `tasks/collaboration-messaging/claude-wake-acceptance.md`, this task list.

**Estimated scope:** Small.

## Checkpoint: Delivery review

- [x] Real-host outcome is recorded without secrets or overclaiming.
- [x] Repository validation and smoke self-test pass.
