# Todo: cleanup-gaps

- [x] Task 1: Retire follows the bridge's unread rule and names what blocks (D59) — `native_collaboration_retire.py` `identity_state` uses `UNREAD_FOR`'s rule (`delivery_state != 'expired'`, only when the column exists; v2 mailboxes unchanged) and returns `blocking` (id, state; `broadcast` for `*`, `queued` for NULL); the refusal adds up to 10 `id state` pairs then "and N more", never bodies. New `DeliveryStateRetireTests` (4) — red before (the expired message 10 counted: "still has 1/2/13", no ids): expired-only → retired; an `accepted` 11 → refused naming "11 accepted", not 10, no body; 12 `unknown` → "12 unacknowledged", 20…29 listed, "and 2 more"; `main` prints "11 accepted" without body. Fixture fixes: the fake node now answers `--version` (the old `main` refusal test passed only because node selection refused; it now also asserts "1 unacknowledged"); `test_mailbox_read_only.py` compares state and count instead of the whole dict (new `blocking` key). validate 33 files / 527 tests, bridge `npm run check` 138 ok (Python 3.10.7)
- [ ] Task 2: Cancel closes a never-turned, host-rejected Codex record (D60)
- [ ] Task 3: bridge_register refuses a retired name unless `reactivate: true` (D61 A)
- [ ] Task 4: Codex follow-up to a retired delegated identity is held (D63)
- [ ] Task 5: Interface and docs (D62)
- [ ] Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`
- [ ] Task 6: Live (temporary `AGENT_RELAY_HOME`/HOME, coordinator told first)
- [ ] Checkpoint (gate): module review
