# Tasks: optional Claude Code CLI tmux wake

Plan: [`claude-tmux-wake-plan.md`](claude-tmux-wake-plan.md)

## Task 1: Start an opt-in tmux-hosted Claude session

**Dependencies:** None.

**Acceptance criteria:**
- [x] Default launch is unchanged; only `--tmux-wake` selects tmux.
- [x] The new session runs Claude through the existing token-safe wrapper using a direct argument
      list; inside tmux there is no nested session.
- [x] Missing tmux and noninteractive launch fail before Claude starts.

**Verification:** Red/green focused launcher tests and a controlled fake-Claude tmux launch.

**Files:** `plugins/spec-guard/hooks/collaboration_claude.py`,
`plugins/spec-guard/hooks/test_collaboration_runtime.py`.

## Task 1b: Expose installed tmux to the opted-in LaunchAgent

**Dependencies:** Task 1.

**Acceptance criteria:**
- [x] A newly generated service plist includes tmux's installed directory without moving the
      pinned npx directory or copying a token into the plist.
- [x] An absent tmux keeps the mailbox service usable; an unsafe relative or path-separator value
      cannot enter the service PATH.
- [x] The installed user service is not changed or restarted as a side effect of code/tests.

**Verification:** Red/green service plist tests; read-only host service status. The user separately
approved refreshing the installed managed service for real-host acceptance.

**Files:** `plugins/spec-guard/hooks/collaboration_runtime.py`,
`plugins/spec-guard/hooks/test_collaboration_runtime.py`.

## Task 2: Explain the one-command user path and delivery limits

**Dependencies:** Tasks 1 and 1b.

**Acceptance criteria:**
- [x] Operator guidance gives the exact opt-in launch and one-step `collab` join, without exposing
      XATS registration fields to the user.
- [x] Guidance says tmux wake is CLI-only, a short hint and not a read acknowledgement; mailbox
      fallback, permissions, Codex Desktop, and ChatGPT in Chrome remain clear.
- [x] A documentation contract test prevents the unsafe Channel flag from becoming the suggested
      normal-user path.

**Verification:** `test_collab_entry.py` and repository validation.

**Files:** `plugins/spec-guard/skills/collaboration-ops/SKILL.md`,
`plugins/spec-guard/references/collaboration-runtime.md`,
`plugins/spec-guard/hooks/test_collab_entry.py`.

## Checkpoint: real-host acceptance

- [x] One idle Claude CLI session self-registers and reports a verified tmux pane binding.
- [x] A peer sends one benign message; target calls `get_inbox` without a manual prompt and replies.
- [x] The acceptance record separates mailbox write, poke, read, and reply without secrets or full
      paths.
- [x] Focused tests and `/bin/bash scripts/validate.sh` pass; scope and rollback are reviewed.
