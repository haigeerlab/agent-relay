# Todo: ops-commands

- [x] Task 1: Body from file (D43) — `src/body-file.ts` `readBodyFile()`: absolute, `lstat` not a symlink, regular, owner, 1 B … 256 KiB; opened `O_RDONLY | O_NOFOLLOW`, `fstat` must match the checked inode, device and size, full read; strict UTF-8 with `ignoreBOM` so the bytes round-trip. `bridge_send` takes exactly one of `body`/`bodyFile`. `test/body-file.test.ts` 3 tests (red before): a body with `$HOME`, backticks, `$(…)`, quotes, backslash, CRLF, tab, globs, CJK, emoji, an inner BOM and no trailing newline read exactly, a leading BOM byte-identical; relative, missing, symlink, directory, empty, 256 KiB + 1, Latin-1 refused, exactly 256 KiB accepted; MCP send stores it unchanged, both/neither/relative refused. Mutation (BOM stripped) → red
- [ ] Task 2: Status and wait by message id (D45)
- [ ] Task 3: whoami (assumption 3)
- [ ] Checkpoint (report): bridge commands green
- [ ] Task 4: doctor (D42)
- [ ] Task 5: `--expires-at` (D44)
- [ ] Task 6: Docs
- [ ] Task 7: Live (coordinator told first)
- [ ] Checkpoint (gate): module review
