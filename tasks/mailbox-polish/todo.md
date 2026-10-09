# Todo: mailbox-polish

- [x] Task 1: the inbox shows the state after its own read (D154) — new `test/mailbox-polish.test.ts`: a message set to `unknown`, fetched by bob through `bridge_inbox` list, `bridge_inbox` part read and `bridge_wait`, must read `accepted` in that same result; red (`list`: actual `unknown`, the page was built before `recordRead`), green after the views are re-read through `deliveryState` after the read is recorded
- [ ] Task 2: a reply is evidence of delivery (D155)
- [ ] Task 3: one-time approval lines and the routing pipe (D156, D157)
- [ ] Checkpoint (report): local validation
- [ ] Task 4: PR and CI
- [ ] Checkpoint (gate): module review
