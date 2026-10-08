# Todo: inbox-read-receipt

- [x] Task 1: only the identity itself records a read (D99, D100) — new `test/read-receipt.test.ts` (two Claude-style sessions on one mailbox): bystander `bridge_inbox` lists the message but returns `readRecorded: false` with the exact D100 note, the message stays `queued` and the owner's `lastSeen` unchanged; the owner's read → `readRecorded: true`, no note, `accepted`, `lastSeen` moves; an empty owner page still says `readRecorded: true`; the same pair for `bridge_wait` with `acknowledge: false`, and an acknowledging wait says true; a bystander's `bridge_outbox` leaves the owner's `lastSeen`, the owner's own moves it. Red 3/3 (field missing, `lastSeen` moved by the bystander), green after `server.ts`: `ownRead` (`caller.owns`) gates `recordRead` / `touch` in the three handlers, `readReceipt` adds the fields, the two descriptions mention them. No other test changed; bridge check 146/146. `UPSTREAM.md` row, manifest, CHANGELOG
- [ ] Task 2: restart cases and the wake bound (D102)
- [ ] Checkpoint (report): bridge check, validate on one Python
- [ ] Task 3: interface 1.4 and docs (D101, D103)
- [ ] Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`
- [ ] Task 4: live check with two clients
- [ ] Checkpoint (gate): module review
