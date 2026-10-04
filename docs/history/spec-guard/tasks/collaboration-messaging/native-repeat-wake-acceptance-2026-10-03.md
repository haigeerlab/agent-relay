# Native same-Mac repeat-wake acceptance — 2026-10-03

Plan: [`native-repeat-wake-plan-2026-10-03.md`](native-repeat-wake-plan-2026-10-03.md)

Status: **two consecutive Claude Code idle wakes from Codex passed on one Mac; the reported
second-wake failure did not reproduce under these conditions, and general promotion remains gated**.

## Baseline and isolation

- Repository evidence was prepared from `origin/main` commit
  `e6368e39ad35827fd1da7c605c78b1ca9140758d` on an independent branch.
- The installed plugin was `v0.38.3`; the native runtime remained pinned to upstream revision
  `8f12c880cfdba73812b6ab7bc0f373fc467e0343`.
- The target was a fresh, persistent Claude Code `2.1.288` CLI session in a disposable Git
  repository. The sender was the current Codex Desktop session. The target explicitly registered
  itself with wake enabled; the sender registered without wake. The Codex Desktop build was not
  independently captured, so this run is not a new qualifying host-version tuple.
- Two exact synthetic identities and one synthetic thread were used. The test read only those
  identities' inboxes. No existing identity, unread delivery, project file, Git state, host
  configuration, permission setting or transport selector was changed.

## Two-round result

1. Codex sent round 1 to the idle Claude identity. The immediate wake receipt was `unknown`, but
   Claude entered a new turn without human input, read the message, replied on the same thread and
   acknowledged it. The sender then read and acknowledged the reply. Both sides had zero unread
   test messages.
2. After Claude returned to idle, Codex sent round 2 to the same identity without re-registering,
   unbinding or typing in the Claude terminal. The immediate receipt was again `unknown`; Claude
   nevertheless entered a second new turn, read, replied and acknowledged. The sender read and
   acknowledged the second reply. The sender outbox recorded acknowledgement timestamps for both
   original messages, and the target's wake history advanced both jobs to `read`.

The `unknown` receipts therefore meant only that the private Claude adapter did not receive a
positive receipt inside its short wait. They did not establish a failed wake. Later read and
acknowledgement were the decisive evidence.

## Product conclusion and remaining boundary

The pinned runtime can repeatedly wake the same live Claude Code session on this host. The earlier
user-visible failure is not reproduced by two consecutive idle sends, so this run does not support
a transport-source fix or a definitive historical root cause. Two known conditions can produce the
reported experience: the target never opted into wake, or its host process stopped (including a
one-shot CLI invocation that already exited). Permission holds and future private-interface drift
remain separate possible failure paths. In all of these cases mail remains durable, but a stopped
target still requires a user to start or resume its host.

The daily `collab` contract now makes one-sentence name/host/project targeting, target-owned wake
opt-in, identity reuse and inconclusive `unknown` handling explicit. This evidence does not satisfy
the separate two-version, two-host, upstream-revision-change and open-defect gates for making native
the product-wide absent-marker default. XATS therefore remains the default for installations that
have not explicitly selected native, and the native transport is retained.
