# Todo: install-truth

- [x] Task 1: doctor `claude-plugin` check (D184) — tests first (red: `_claude_plugin`/`_overall` missing): matching copies ok whatever the listing's `version`; the measured shape warns about the `installPath` copy only, with both commands and the restart; local entries sharing a copy are one line naming their projects, a missing project folder marked "(folder gone)"; a copy without a readable `plugin.json` warns; disabled entries and other plugins ignored; no entries ok; no `claude`, non-zero exit, non-JSON, non-list → `skip` with the reason; `skip` leaves the overall state alone. Read-only run on this Mac: warn — cache `0.1.0` used by local scope in 8 projects (4 folders gone), cache `0.5.2` by user scope and local scope in 2 projects; the clone (0.6.1) matches
- [ ] Task 2: skills give exact arguments (D185)
- [ ] Task 4: real check of the Claude plugin update on this Mac (ask the user first)
- [ ] Task 3: README and CHANGELOG, from Task 4's measurement
- [ ] Checkpoint (report): local validation
- [ ] Task 5: PR and CI
- [ ] Checkpoint (gate): module review
