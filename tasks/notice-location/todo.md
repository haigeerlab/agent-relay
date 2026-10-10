# Todo: notice-location

- [x] Task 1: where a session is (pure, tested) — `test/location.test.ts` first (red: no module): `locate` gives desktop, terminal (tty + owning bundle), background (8-hex id), unknown; strict `validTty` / `validBundle`; `outermostApp` takes the outermost `.app` of a nested path and nothing for tmux; the registry reader keeps `entrypoint`, `kind`, `hostSessionId` as strings of at most 64 characters
- [x] Task 2: the text says where — tests first: approval subtitle `#id · agent · <session> in <project> · <place>`, without previews only the category; Codex subtitle gains `· Codex app` only for a confirmed app; found while building: the terminal app's display name went into the subtitle uncleaned (a newline in it split the argument record) — the label is now cleaned and cut like every shown name; the osascript fallback shows the same text
- [x] Task 3: the click goes there — tests first: `-activate` for desktop, Codex app and other terminal apps; one fixed `-execute` for Terminal and iTerm whose only paths are `/usr/bin/open`, `/usr/bin/osascript` and the tty device; nothing for background, unknown, plain Codex, a terminal without an app, a malformed tty or bundle; hostile session, project, sender and app names never reach the action. Wiring: approval notices look the place up once per notice (none for a notice already marked); a Codex notice is "Codex app" when the wake result was `busy` (the app answered on its socket) or, for an unbound recipient, when `codexOwner` is true. Bridge `npm run check` green
- [ ] Task 4: real checks on this Mac (ask the user before each)
- [ ] Task 5: docs and bridge bookkeeping
- [ ] Checkpoint (report): local validation
- [ ] Task 6: PR and CI
- [ ] Checkpoint (gate): module review
