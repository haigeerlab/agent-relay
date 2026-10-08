# Plan: upgrade-restart-note

Based on [`spec/upgrade-restart-note.md`](../../spec/upgrade-restart-note.md) (accepted by the user on 2026-10-09:
assumptions 1–5, D132–D134). Branch `claude/upgrade-restart-note` from main 676ad9c. Docs only. The round-2
coordinator reviews the PR; the user merges after every CI check has finished green.

## Task List

### Task 1: README, skill and CHANGELOG (D132–D134)
README "升级运行时": the two ways to stop the bridges and the ChatGPT restart after `pkill`, with the bracketed
`pkill`; collaboration-ops skill: the same plus the consent rule; CHANGELOG `[Unreleased]`.

### Checkpoint (report): validate on one Python

### Checkpoint (gate): module review
Then push and PR with the user's approval; the round-2 coordinator reviews; the user merges after CI has finished green.
