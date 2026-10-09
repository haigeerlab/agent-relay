# Todo: presence-polish

- [x] Task 1: approval notice once per waiting episode (D175) — found while building: several bridges run on one mailbox (twelve on this Mac), so an in-memory first-seen time would give each its own key and up to one notice per bridge; the start is kept next to the notice marks instead (`notified/episode-<session>`, written `wx`, removed when the session is seen not waiting), and because a session leaves `claudeWaiting` once its message is handled (nothing ends the episode then), the since-less key also carries the message id. Test first (`approval-notice.test.ts`, red: a second episode without `statusUpdatedAt` was never told): two dispatchers on one mailbox, one episode → one notice; not waiting, then waiting again → told again; message handled, a new one waits → told once. With `statusUpdatedAt` the key is unchanged (existing test). UPSTREAM row + manifest
- [ ] Task 2: presence only for bound sessions, unknown when unreadable (D176)
- [ ] Task 3: retired identities are not looked up (D176)
- [ ] Task 4: offset errors, expired reads labelled (D177)
- [ ] Checkpoint (report): local validation
- [ ] Task 5: PR and CI
- [ ] Checkpoint (gate): module review
