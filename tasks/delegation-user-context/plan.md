# Plan: delegation-user-context

Based on [`spec/delegation-user-context.md`](../../spec/delegation-user-context.md) (accepted by the user on
2026-10-09: assumptions 1–5, D162–D165). Branch `claude/delegation-user-context` from main 4964979. Sixth module of the
round-2 batch (0.6.0). Python only.

## Task List

### Task 1: the option is recorded (D162)
Red first: `evaluate_authorization` accepts `host_permission = "user-environment"` for a Claude target, rejects it for a
Codex target (`user-environment-claude-only`) and rejects any other value; the digest differs with it; stored rows keep
validating. CLI `create --user-environment` / `permissions --user-environment`; public results show it.

### Task 2: the launch (D163)
Red first: `build_create_command` without the option equals today's argv; with it, `--setting-sources
user,project,local`, no `--disable-slash-commands`, `Skill` in `--tools`, the rest identical.

### Task 3: the preflight matches the launch (D164)
Red first: with a fixture `CLAUDE_CONFIG_DIR` user allow and none in the project, default preflight not ready with the
note, user-environment preflight ready; a user deny blocks only with the option; `permissions` names the files read;
`continue` uses the recorded choice.

### Task 4: skill, README, CHANGELOG (D165)

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14.

### Task 5: PR and CI
Push and open the PR; the four CI jobs green.

### Checkpoint (gate): module review
The user reviews and merges; the real-host acceptance (spec requirement 6) is run by the coordinator after the batch.
