# Todo: post-090-docs

- [x] Task 1: request-closing follow-ups (D256) — test 122 renamed for the sequential pre-check; the lost-race test asserts no read for the skipped request (held at once: the code already did not record it); `spec/request-closing.md` revision assumption 4 reworded; the three "Open:" lines in `tasks/request-closing/todo.md` marked done with their decisions; `UPSTREAM.md` row and manifest (test-only, runtime-file lines unchanged — checked)
- [x] Task 2: doctor cleanup advice (D257) — 4 tests first plus the folder-gone count case reworded (5 red), then `_plugin_labels`: user steps first, one quoted command per folder sorted, a note and no command for a live project-scope record; the folder-gone note says they can stay and how to remove one (wording taken from the 2026-10-23 measurement: `git init` when the folder sits inside another repository); `test_doctor` 56 ok; `spec/claude-plugin-label.md` change-log line
- [x] Task 3: README, RELEASING, CHANGELOG (D257, D258) — doc guard in `test_packaging.py` (red), then README zh/en "更新插件" (clone install: the two label-refresh commands; folder-gone and project-scope sentences), RELEASING "从上一版升级" rule and "发版后" step 1, CHANGELOG `[Unreleased]`; the claude-plugin-label module-review checkpoint was already ticked on 2026-10-23
- [ ] Checkpoint (report): local validation
- [ ] Task 4: PR and CI
- [ ] Checkpoint (gate): module review
