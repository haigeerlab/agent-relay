# Todo: mailbox-polish

- [x] Task 1: the inbox shows the state after its own read (D154) — new `test/mailbox-polish.test.ts`: a message set to `unknown`, fetched by bob through `bridge_inbox` list, `bridge_inbox` part read and `bridge_wait`, must read `accepted` in that same result; red (`list`: actual `unknown`, the page was built before `recordRead`), green after the views are re-read through `deliveryState` after the read is recorded
- [x] Task 2: a reply is evidence of delivery (D155) — test first (store level, `mailbox-polish.test.ts`): bob's `replyTo` reply moves an `unknown` original to `accepted` and its wake job to `read`; carol's reply to bob's message is refused and an unrelated send from bob leaves another `unknown` original as is; a reply to a broadcast leaves it without a delivery state. Red (still `unknown`), green after `insertMessage` records the original as fetched when the replier is its recipient. Bridge `npm run check` 165 green
- [ ] Task 3: one-time approval lines and the routing pipe (D156, D157)
- [ ] Checkpoint (report): local validation
- [ ] Task 4: PR and CI
- [ ] Checkpoint (gate): module review
