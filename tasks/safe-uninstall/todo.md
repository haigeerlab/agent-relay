# Todo: safe-uninstall

- [x] Task 1: Codex removal with approval subtables and a line report (assumptions 1, 2) — `remove_codex_table` now splits the file into TOML tables and compares ours (bare or quoted `mcp_servers.agent_relay`, its `.env`, `.tools.<name>`) key by key with the fragment: `tools.<name>` tables may hold only `approval_mode = <quoted string>` (comments and blank lines allowed); `command` may differ when it names an absolute executable; every other difference refuses with `line N: unexpected key K` / `K differs` / `missing K` / `unexpected table` / `duplicate table` — key names and line numbers only, never values (they may be credentials). All our tables are removed wherever they are; neighbours stay byte-for-byte (the seam rule of the old code). Existing tests kept; the `edited` case now changes an env value instead of the node path (deliberate: a node path change is now accepted when executable). New `ApprovalSubtableTests` 4 tests (red before): this Mac's five-subtable shape; subtables elsewhere with a quoted name, a comment and `'prompt'`; executable vs missing node path; six refusal cases naming the lines, file unchanged, the value `tok-123` never in the message. Found after the first commit: the new class sat below the file's `unittest.main()` guard, so `validate.sh` (which runs each file as a script) skipped it; the guard moved to the end (`be0ace4`), validate 458
- [ ] Task 2: Backups before every host write (assumption 3)
- [ ] Checkpoint (report): Codex removal and backups green
- [ ] Task 3: Claude deny rules removed on uninstall (D46)
- [ ] Task 4: Runtime uninstall keeping history (D47)
- [ ] Task 5: Docs (D48)
- [ ] Task 6: Live (temporary `AGENT_RELAY_HOME` and HOME, coordinator told first)
- [ ] Checkpoint (gate): module review
