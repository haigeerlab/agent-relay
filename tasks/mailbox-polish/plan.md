# Plan: mailbox-polish

Based on [`spec/mailbox-polish.md`](../../spec/mailbox-polish.md) (accepted by the user on 2026-10-09: assumptions
1–5, D154–D157). Branch `claude/mailbox-polish` from main 7e29b8a. Fourth module of the round-2 batch (0.6.0). Every
bridge commit carries its `UPSTREAM.md` row and the regenerated manifest.

## Task List

### Task 1: the inbox shows the state after its own read (D154)
Red first: a message whose wake ended `unknown` reads `accepted` in the inbox call (list and part read) and the
`bridge_wait` call that fetch it.

### Task 2: a reply is evidence of delivery (D155)
Red first: the recipient's `replyTo` reply moves an `unknown` original to `accepted` and closes its wake job as `read`;
a reply to a broadcast, or a send without `replyTo`, does not.

### Task 3: one-time approval lines and the routing pipe (D156, D157)
Red first (Python): `native_collaboration_adapters.py claude-allow-rules` prints the ten exact rules once each and a JSON
snippet that parses, writing nothing. Then collab (first-join note), session-routing (pipe), README (incl. the trust
dialog), CHANGELOG.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14.

### Task 4: PR and CI
Push and open the PR; the four CI jobs green.

### Checkpoint (gate): module review
The user reviews and merges; the real-host acceptance (spec requirement 6) is run by the coordinator after the batch.
