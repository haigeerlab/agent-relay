# Todo: codex-approval-presence

- [x] Task 1: confirm the pending-request shape on the real host (read only; the user approves the test task's approval setting first) — command approval seen: `requests[]` entry `{method, id, params}`, method as in assumption 2, no `completed` (answered entries are removed), time in `params.startedAtMs`; extra signal `threadRuntimeStatus.activeFlags: ["waitingOnApproval"]`; per-task approval switch exists, temporary config removed; file-change, user-input and ping-while-pending not checked (see plan notes)
- [ ] Checkpoint (gate): shape matches the spec
- [ ] Task 2: `CodexIpc` can send a broadcast and receive the one follower snapshot it asked for (D234, D235)
- [ ] Task 3: classify pending requests (D233)
- [ ] Task 4: the Codex lookup follows, reads and unfollows within 2 s (D232, D234, D235)
- [ ] Task 5: the views (D232)
- [ ] Checkpoint (report): bridge green
- [ ] Task 6: interface 2.6, docs and bookkeeping (D236)
- [ ] Checkpoint (report): local validation
- [ ] Task 7: PR and CI
- [ ] Checkpoint (gate): module review
