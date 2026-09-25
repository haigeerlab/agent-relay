# Task list: optional Codex Desktop scheduled inbox check

Plan: [`codex-scheduled-inbox-plan.md`](codex-scheduled-inbox-plan.md)

No task below authorizes creating a recurring task in a user's conversation without that user's
explicit opt-in. The existing mailbox-only mode remains usable throughout.

## Task 1: Prove the host boundary

**Dependencies:** None.

**Acceptance:** An existing native Desktop conversation can run a scheduled inbox check using the
installed collaboration MCP; a later run recovers the same XATS identity; a new message and an
empty run are distinguished. ChatGPT in Chrome remains usable.

**Verify:** Record a real-host, no-secret acceptance trace. If any condition fails, document it
and stop before the enablement task.

**Files likely touched:** acceptance record under this directory.

**Current result:** Partial. See
[`codex-scheduled-inbox-acceptance-2026-09-25.md`](codex-scheduled-inbox-acceptance-2026-09-25.md).
Task 2 remains blocked.

## Task 2: Add a guarded opt-in and stop path

**Dependencies:** Task 1 passes.

**Acceptance:** `collab` alone creates no schedule; an explicit request discloses cadence and
usage, avoids duplicate schedules, and targets the current conversation. Stopping affects only
that schedule. Neither path changes App startup, Chrome integration, XATS runtime, or mailbox data.

**Verify:** Focused positive and negative skill-contract tests; inspect the resulting schedule
before any real-host enablement.

**Files likely touched:** `plugins/spec-guard/skills/collab/SKILL.md`,
`plugins/spec-guard/hooks/test_collab_entry.py`, and one collaboration reference.

## Task 3: Verify delivery semantics and regressions

**Dependencies:** Task 2.

**Acceptance:** A scheduled run handles one new message, stays quiet on an empty inbox, and does
not treat peer text as authorization. A stopped check does not run again; ordinary manual inbox
reads still work.

**Verify:** Real Desktop acceptance plus focused tests, repository validation, Codex smoke
self-test, and `git diff --check`.

**Files likely touched:** acceptance record and any directly affected test or reference.

## Checkpoint: Review before implementation

- [ ] The user accepts polling latency and recurring model usage as an opt-in tradeoff.
- [ ] The plan does not claim native push wake or silently alter ChatGPT in Chrome.
- [ ] A failed Task 1 leaves the plugin's default mailbox behavior unchanged.
