# Todo: wake-any-mode

- [x] Task 1: the bridge stops overriding woken Codex turns (D140, D141) — tests first: `codex-wake.test.ts` now expects `request` to be exactly `{threadId, input: []}` (the D65 approval/sandbox fields gone, `untrusted_input` kept) and `wakeCodex(job, path)` with no gate argument (the `unverified`/held mode removed); new `codex-any-mode.test.ts` (3: an auto-approved Codex session is woken once with no after-turn check and no notice; a `codex-gate.off` left by an older bridge neither holds the wake nor is deleted, and no gate-off notice; an auto-approved Codex session still binds wake, D66); `codex-gate.test.ts` deleted (its 7 gate tests); `notify.test.ts` loses the gate-off assertions and the D89a cut test uses a non-gate reason. Red: typecheck failed on the new `wakeCodex` signature. Then: `codexTurn` request back to the pre-D65 shape; `codex-gate.ts` deleted; the dispatcher calls `codexWake(job)` with no gate, no rollout check and no `codex-gate.off`; `notify.ts` loses `event: "gate-off"`; `WakeResult.turnId` (only for the after-turn check) removed; the Codex `held` bounce text no longer names a gate. Bridge `npm run check` green: 151 tests (155 − 7 + 3)
- [ ] Task 2: doctor and interface (D144, D145)
- [ ] Task 3: skills, README and CHANGELOG (D142, D143, D144)
- [ ] Checkpoint (report): local validation
- [ ] Task 4: PR and CI
- [ ] Checkpoint (gate): module review
