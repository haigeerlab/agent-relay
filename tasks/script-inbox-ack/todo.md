# Todo: script-inbox-ack

- [x] Task 1: shared inbox read (D271) — `readInbox` in `src/inbox-read.ts`, `bridge_inbox` calls it; `readReceipt` shared with `bridge_wait`; existing inbox tests green unchanged (19)
- [x] Task 2: parse `inbox` and `ack` (D271, D272) — 3 tests in `cli.test.ts` red first (fields, refusals incl. `--from` on inbox/ack, help), then `cli-logic.ts` and the help text
- [x] Task 3: run `inbox` and `ack` as a script identity (D271–D273) — 4 tests in `script-cli.test.ts` red first (read recorded, long body via CLI continue line, ack of direct + broadcast leaves 0 unread, session/unknown/retired refused with nothing changed); `requireScriptIdentity` shared with `send` (its test now expects the session wording)
- [x] Task 4: wording (D274) — 4 assertions red first, then D251 warning, `identity.ts` refusal, register preview, `sessions` note
- [x] Task 5: interface 2.11 and docs (D275) — `test_packaging.py` red first, `interface.json`, `relay_status.py`, interface doc §1/§2.4/`bridge_send` row, README zh/en (known issue removed, script section, retire paragraph on broadcasts, glossary, interface number; the 0.9.5 status line is left for the release), collaboration-ops skill, both CHANGELOGs, UPSTREAM rows, manifest
- [x] Checkpoint (report): bridge green — `scripts/validate.sh` pass: 48 files, 968 tests (bridge `npm run check` 334)
- [ ] Checkpoint (gate): PR review and merge — user merges; result to the owner session
