# Todo: claude-plugin-label

- [x] Task 1: doctor reports a stale label (D246, D247) — tests first (5 red: the measured shape, no user record, a lagging user label, gone folders only, `readFromFolder` with a stale `installPath`), then green; `_plugin_labels` added, the old "not loaded while readFromFolder is set" note merged into it; the fixture's default label now follows the record's `installPath` copy (as measured), so the D184 test that asserted "the label is ignored" became "a matching label is ok" and the newer-copy test got a consistent label; `test_doctor` 49 ok. Read-only on this Mac: `warn` with labels 0.6.1 (3 projects), 0.1.0 (3), 0.5.2 (1), 5 gone records counted, 7 uninstall steps. Found: the spec's "6 of the 12 local records" gone is wrong — 5 are gone and 7 live; left in the approved spec until the next review
- [x] Task 2: README zh/en, `collab`, `collaboration-ops`, CHANGELOG `[Unreleased]` — guard test first (red), then the text; README's "old cached copies are listed only for reference" replaced, since they now warn as labels
- [ ] Checkpoint (report): local validation — `scripts/validate.sh` on Python 3.9, 3.10, 3.14; doctor's `claude-plugin` on this Mac recorded
- [ ] Task 3 (gate): host measurements (a)–(c) — after the 0.9.0 freeze ends and the user consents to each step
- [ ] Task 4: PR and CI
- [ ] Checkpoint (gate): module review
