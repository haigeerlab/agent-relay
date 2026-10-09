# Plan: long-messages

Based on [`spec/long-messages.md`](../../spec/long-messages.md) (accepted by the user on 2026-10-09: assumptions 1–5,
D150–D153). Branch `claude/long-messages` from main 1013731. Third module of the round-2 batch (0.6.0). Every bridge
commit carries its `UPSTREAM.md` row and the regenerated manifest.

## Task List

### Task 1: the send result carries no body (D150)
Red first: `bridge_send` with a 160 000-byte `bodyFile` returns no `body`, the right `bodyLength`, a result under
2 000 characters; the duplicate path likewise.

### Task 2: budgets in token-safe units (D151)
Red first in a paging test: Chinese pages stay within 48 000 units, English pages unchanged, no split surrogate pair.

### Task 3: read a long body in parts, and say how (D152, D153)
Red first: a 160 000-byte Chinese body read with `messageId` + `bodyOffset` comes back whole and in order, every piece
within the default budget, the last without `nextOffset`; another agent's message is refused; shortened bodies in
inbox, thread and wait carry `nextOffset` and the continue line.

### Task 4: skill, tool descriptions, README, CHANGELOG
collab: how to read a long message without Bash; `bridge_inbox` / `bridge_send` descriptions; README; CHANGELOG.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14.

### Task 5: PR and CI
Push and open the PR; the four CI jobs green.

### Checkpoint (gate): module review
The user reviews and merges; the real-host acceptance (spec requirement 7) is run by the coordinator after the batch.
