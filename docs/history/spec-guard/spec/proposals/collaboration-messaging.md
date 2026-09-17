# Proposal: Add local collaboration messaging
<!-- spec-guard-proposal:v2 id=collaboration-messaging revision=sha256:91ea56bbada0acba5a0682f944e89cb7ede0c34ed7cf4f435fe39cc2c67888dd -->

## Summary

Provide an optional same-Mac mailbox for Claude Code and Codex sessions to exchange free-text technical
messages across or within repositories. This is an independent capability because it owns a private local
runtime, host adapters, and recovery boundaries; it does not alter the existing Proposal lifecycle.

## Integration intent

| Field | Value |
| --- | --- |
| Problem | Claude Code and native Codex Desktop lack a shared, durable local conversation bridge. |
| In scope | A loopback-only XATS runtime, no-secret Claude and Codex adapters, persistent mailbox delivery, explicit lifecycle operations, and stale registry cleanup. |
| Out of scope | Git or Issue mutation, task assignment workflow, project grouping, cross-machine networking, and Codex managed app-server wake mode. |
| Safety boundaries | Keep the runtime on loopback, keep token material in private files and child environments, require explicit destructive cleanup targets, and preserve ChatGPT in Chrome. |
| Initial dependency assumptions | The capability is independent of existing Proposal modules and only shares the plugin packaging and local command conventions. |
| Acceptance intent | Real ordinary Claude Code and native Codex Desktop sessions exchange and read persistent messages without manual copy-paste; tests prove token, loopback, and recovery constraints. |

## Capability map baseline

| Field | Value |
| --- | --- |
| Remote | origin |
| Default branch | main |
| Commit | fc70060cfd57e94a6b95fe0ec04fadff66aef1b3 |
| Capability map | spec/CAPABILITY-MAP.md |
| Goal digest | 06b3ede4f7a1 |
| Build order | proposal-contract → proposal-publication → proposal-tracker-read → proposal-review → proposal-mainline-review → proposal-promotion-proof → proposal-boundary-guidance |

### Module digests

| Module id | Row digest |
| --- | --- |
| proposal-contract | f84b24340ec2 |
| proposal-publication | e563ad8b3b2b |
| proposal-tracker-read | 7e155de3579e |
| proposal-review | f8e8cdcfb46b |
| proposal-mainline-review | 403f2901bd0d |
| proposal-promotion-proof | b236226e282f |
| proposal-boundary-guidance | 491564a83c5b |

## Change

| Field | Value |
| --- | --- |
| Type | new-module |
| Module id | collaboration-messaging |
| Responsibility | Provide a private same-Mac mailbox and host adapters for direct Claude Code and Codex session communication. |
| Depends on | — |
| Build-order anchor | end |

## Tracker contract

| Field | Value |
| --- | --- |
| Proposal id | collaboration-messaging |
| Identity label | proposal |
| Stage label namespace | proposal-stage: |
