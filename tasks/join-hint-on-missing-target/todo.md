# Todo: join-hint-on-missing-target

- [x] Task 1: the selector's `nextStep` — red first (the constants did not exist: import error), then `JOIN_SENTENCE`, `JOIN_HINT` (108 characters) and one line in `_decision` for the three reasons. Tests: the three reasons on both host directions carry exactly `JOIN_HINT`; sixteen other results carry no `nextStep`; a name field is rejected; the text is a valid public `nextStep`; the CLI prints it as ASCII JSON (kept `json.dumps`' escapes so a C-locale stdout cannot fail) and `json.loads` gives the text back
- [x] Task 2: the skills pass it on — red first (two failures), then `skills/session-routing/SKILL.md` (the `stop` bullet, the zero-match line) and `skills/collab/SKILL.md` (the zero-match line); both quote `JOIN_SENTENCE`, compared by the entry tests. No Codex copy of either text exists (`references/collaboration-protocol.md` only says "stop with a minimal next step": unchanged)
  - Corrected while building: my first wording said the user's text "goes into no command", which contradicts the existing read-only `resolve --name '<名字>'` step. Now: "this step adds no command carrying the user's text"; the capability-map row and spec assumption 4 say the same
- [x] Task 3: CHANGELOG `[Unreleased]`
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH: 47 files / 775 tests each (770 before, five new)
- [x] Task 4: PR and CI — #96 (c794586), the four CI jobs green
- [x] Checkpoint (gate): module review — the round-2 coordinator reviewed #96 (accepted the ASCII-escaped CLI output and the corrected wording about the user's text; will check the relayed sentence word for word in the acceptance); the user merged #96 (8b0d959)
