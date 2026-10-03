# Proposal: Add bounded local session delegation
<!-- spec-guard-proposal:v2 id=authorized-session-delegation revision=sha256:01dba511adc0c03803e3174b25136434a5f05d72cfb85aead9ac08aa1b974615 -->

## Summary

Let an explicitly requested Claude Code or Codex session create one or more bounded same-Mac review or development sessions, coordinate them through the existing collaboration mailbox, and return traceable results without repeated confirmation inside the approved task. This is a separate capability because session creation, authorization lifetime, worktree isolation, retry identity, and cleanup are intentionally outside the communication-only contract.

## Integration intent

| Field | Value |
| --- | --- |
| Problem | The mailbox can connect sessions that already exist, but it cannot safely create a reviewer, carry a bounded task authorization, or recover a partially created delegation without either repeated user prompts or hidden orchestration. |
| In scope | Same-Mac Claude Code and Codex host-native session creation; task, batch, and session-lifetime authorization; review, bounded-development, and host-native permission profiles; joined-session directory display; single-hop delegation; idempotent creation and retry; result provenance; cancellation and cleanup. |
| Out of scope | Cross-machine networking, general task scheduling, recursive worker trees, automatic project topology, restoring retired parallel commands, enabling upstream worker/review/orchestration tools, permanent global silent authorization, and implicit Git, Issue, PR, MR, release, or user-configuration writes. |
| Safety boundaries | A user's explicit natural-language request authorizes only the resolved task envelope; self-proposed launches ask once; host permissions may narrow but never widen the envelope; ordinary mailbox text cannot grant or expand authority; broad auto-approved sessions cannot bind general mailbox wake; writes use an isolated worktree; scope expansion and consequential external actions ask again. |
| Initial dependency assumptions | Reuse `collaboration-messaging` only for discovery, durable delivery, wake status, replies, and acknowledgements; use each host's supported session-creation and permission mechanisms rather than the bridge's hidden worker surface. |
| Acceptance intent | On one Mac, ordinary Claude Code and Codex sessions can each initiate an authorized reviewer on the other host, receive a result tied to the selected project and revision, continue bounded follow-up without repeated prompts, and recover wake, creation, registration, timeout, ambiguity, and cancellation failures without duplicate sessions or false success claims. |

## Capability map baseline

| Field | Value |
| --- | --- |
| Remote | origin |
| Default branch | main |
| Commit | e6368e39ad35827fd1da7c605c78b1ca9140758d |
| Capability map | spec/CAPABILITY-MAP.md |
| Goal digest | 03cd446c69f5 |
| Build order | proposal-contract → proposal-publication → proposal-tracker-read → proposal-review → proposal-promotion-proof → collaboration-messaging → collaboration-safe-defaults → local-ticket-ledger → ledger-dependency-lock → local-convention → phase-and-verification → module-insert → capability-history → documentation-baseline → documentation-impact → documentation-verification → audit-remediation → done-stage-split → module-interrupt → plan-without-todo → proposal-pool-isolation → proposal-label-acceptance → proposal-add-module-promotion → proposal-submit → promotion-proof-diagnostics → insert-existing-spec → ledger-worktree-owner → done-unmerged-hint → git-fixture-template → local-ticket-portability → retired-module-separation → audit-handoff → hosted-ticket-workflow |

### Module digests

| Module id | Row digest |
| --- | --- |
| proposal-contract | f84b24340ec2 |
| proposal-publication | e563ad8b3b2b |
| proposal-tracker-read | 7e155de3579e |
| proposal-review | f8e8cdcfb46b |
| proposal-promotion-proof | 6d0cdfcf3656 |
| collaboration-messaging | 2a091b441012 |
| collaboration-safe-defaults | fa11d17d3934 |
| local-ticket-ledger | 75ed35684de9 |
| ledger-dependency-lock | bc3f8bbc3b88 |
| local-convention | bd5ffdd20fdf |
| phase-and-verification | 299bdf8b6c4f |
| module-insert | 4cc89d8f78a4 |
| capability-history | 83a5c722e8ac |
| documentation-baseline | 80dbe13f6626 |
| documentation-impact | 866e51ab31da |
| documentation-verification | 8cdc2b63fb9b |
| audit-remediation | 256eb0614aee |
| done-stage-split | d67afc026e5b |
| module-interrupt | 3e3e44278a97 |
| plan-without-todo | 21280242c951 |
| proposal-pool-isolation | 32cee16b8f9d |
| proposal-label-acceptance | 53184b625ccc |
| proposal-add-module-promotion | 97861b18bdf8 |
| proposal-submit | 10b6be5202b3 |
| promotion-proof-diagnostics | 20ab47b3f8e0 |
| insert-existing-spec | 4cdf90f9133d |
| ledger-worktree-owner | 49f7ed5e6610 |
| done-unmerged-hint | 062ea6636717 |
| git-fixture-template | db1c3f2cc74a |
| local-ticket-portability | cdfd994a5018 |
| retired-module-separation | 67deaf21283a |
| audit-handoff | 73d62ca69073 |
| hosted-ticket-workflow | 3c5a2a094702 |

## Change

| Field | Value |
| --- | --- |
| Type | new-module |
| Module id | authorized-session-delegation |
| Responsibility | Create and coordinate bounded same-Mac Claude Code or Codex review and development sessions under explicit task, batch, or session authorization. |
| Depends on | collaboration-messaging |
| Build-order anchor | end |

## Tracker contract

| Field | Value |
| --- | --- |
| Proposal id | authorized-session-delegation |
| Identity label | proposal |
| Stage label namespace | proposal-stage: |
