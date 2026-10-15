# Todo: upgrade-codex-restart-check

- [x] Task 1: the upgrade output — red first (`RESTART_NEXT` did not exist), then an `upgraded` result carries `next` (quit the ChatGPT app with ⌘Q and reopen; new Claude Code sessions use the new runtime); `current` carries none
- [x] Task 2: the doctor check — red first, then `codex-restart` in `native_collaboration_doctor.py`: the newest `runtime.previous-<YYYYMMDDTHHMMSSZ>[-n]` against the oldest ChatGPT app process (`chatgpt_started`: `ps -axo lstart=,command=` with `TZ=UTC`, exact executable path, helpers excluded). Before → `warn` with `RESTART_NEXT`; after → `ok`; no app, no upgrade on record, unreadable stamp or `ps` failure → `ok` saying so. The +08:00 case (app 11:00 local = 03:00 UTC, upgrade 09:00 UTC) warns; a space-padded day parses. Existing doctor tests inject `chatgpt_started` so they never read this Mac's processes
- [x] Task 3: bookkeeping — README "升级运行时", CHANGELOG `[Unreleased]`
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH (47 files, 794 tests each)
- [x] Task 4: real check, 2026-10-16 — the worktree's doctor against the real runtime (read only): `codex-restart` ok, "the ChatGPT app started after the runtime upgrade at 2026-10-15 10:04:55 UTC" (the app was reopened at 18:07:26 +08:00, read as 10:07:26 UTC)
- [ ] Task 5: PR and CI
- [ ] Checkpoint (gate): module review
