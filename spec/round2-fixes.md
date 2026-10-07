# Spec: round2-fixes

## Objective

Fix the release blockers integration round 2 found
([record](https://github.com/haigeerlab/agent-relay/blob/claude/round2-record/docs/acceptance/2026-10-07-round2.md)):
a delegated Claude target always returns its result through the mailbox (R2-6); the delegation controller and
`doctor` run the bridge with the node the host entries pin, or refuse with "Node too old" before touching a host
(R2-7, R2-1); state migration and reinstall-after-uninstall work under macOS's system Python 3.9, with the supported
Python range stated and tested (R2-9); and `uninstall-claude` does not expose the upstream worker tools to sessions
that are still open (R2-10).

Readers: the user; the round 2 coordinator ("第二轮联调"), who re-runs C3, Claude → Codex without `--node`, D7 and
the reinstall with system Python before release.

## What exists today (measured, main d56a68b, 2026-10-07)

- **R2-6.** `session_delegation_claude._bounded_prompt` appends an `<agent-relay-control>` envelope telling the target
  to call `bridge_register`; nothing says what to do when the mailbox tools are not there yet. Each create/continue
  starts `claude --background … --mcp-config … --tools <Read,Grep,Glob[,Edit,Write,Bash]>,<mailbox tools>`; Claude Code
  connects MCP servers asynchronously, and no documented option makes a background session wait for them before the
  first turn. A quick task is answered while `agent-relay` is still connecting; the target never registers or sends,
  ends `status=idle`, `state=working`, and the next continue is `held` `target-busy` (or `status` →
  `mailbox-registration-missing`).
- **R2-7.** `session_delegation_control._selected_backend` uses `args.node or shutil.which("node")`. With nvm v12 first
  in PATH the private delegation server dies in the MCP handshake; create fails `mcp-catalog-invalid` after the host
  was touched, leaving envelopes `unknown` that `status`/`cancel` cannot clear (e168ea, 269770).
- **R2-1.** `native_collaboration_runtime.py doctor` has `--node` default `node`; the probe uses PATH's node, not the
  host entries' (`/Users/vilin/.nvm/versions/node/v24.18.0/bin/node`), and reports `probe: fail` for a working runtime.
- **R2-9.** Reproduced with a minimal script: `/usr/bin/python3` 3.9.6 (SQLite 3.43.2) cannot open a WAL-mode
  database with `mode=ro` when no `-wal`/`-shm` sits beside it ("unable to open database file"). `state_migration`
  hits this in its second `_sqlite_copy` (reading the backup copy the backup API wrote); `_reinstall_around_history`
  hits it in `_mailbox_counts` on the kept mailbox. `test_state_migration.py`: 3 errors on 3.9.6, green on 3.10.7 and
  3.14.3. `test_mailbox_busy_timeout.py` fails on 3.14.3: under its newer SQLite the reader is not blocked by the
  fixture's `locking_mode = EXCLUSIVE` transaction, so the test proves nothing there (fixture, not product). README
  says only "Python 3".
- **R2-10.** `uninstall-claude` already removes the MCP entry before the seven deny rules (D46), but a session that is
  still open keeps its running bridge; once the rules go, that session offers `ask_codex`, `review_with_codex`,
  `bridge_orchestrate_codex`, `bridge_continue_codex`, `bridge_orchestration_status`, `bridge_orchestration_wait`,
  `bridge_retire`.
- Bridge `package.json` `engines.node` is `>=22.5.0`: the mailbox store uses the built-in `node:sqlite` module, which
  first shipped in Node 22.5.0; older Node fails earlier still, as v12 did on optional chaining (`?.`).

## Assumptions

Confirmed by the user on 2026-10-07.

1. R2-9's cause is the read-only open of a WAL-mode file without its `-shm` under older SQLite; the 3.14 migration
   comparison failure in the record no longer reproduces after PR #10; the 3.14 busy-timeout failure is the test
   fixture's.
2. The minimum Node is 22.5.0, from the bridge's `engines`.
3. No documented Claude Code option makes a `--background` session wait for MCP servers before its first turn, so R2-6
   is fixed by the envelope and a controller fallback, and proven only by live runs.
4. R2-10 comes from Claude sessions still open, not from the order of removal and not from running bridges: in round 2
   all ten bridges had been stopped, and the open session still listed the seven worker tools as soon as the rules
   went, because the host re-filters its cached tool catalogue against the new settings (coordinator, 2026-10-07).

## Decisions

D49–D52 accepted on 2026-10-07 (D52 revised after the coordinator's review, D49's fallback widened to the registered case at plan review).

- **D49 the result route is always used (R2-6).** The envelope tells the target: call `bridge_register` before
  anything else; if the mailbox tools are not listed yet, wait for them (loading them by name with ToolSearch is
  allowed) and only then answer; never answer only in the conversation. ToolSearch joins the target's `--tools` list if
  it is needed for that. Fallback: when `continue` finds the target idle and not registered, the controller reports
  `registration-missing` and re-sends the envelope once, instead of holding it as `target-busy`.
- **D50 one node for every bridge start (R2-7, R2-1).** Order: explicit `--node` → the command in the Claude user entry
  (`~/.claude.json` `mcpServers.agent-relay`) → the command in the Codex table → PATH's `node`. The chosen node's version
  is checked first; below 22.5.0 the command refuses with `node-too-old` (naming the path, the version, and the reason:
  the mailbox needs `node:sqlite`, added in Node 22.5.0) before any host or envelope is touched. `doctor`'s probe uses the same order and reports which node and version it used.
- **D51 Python 3.9–3.14 (R2-9).** Private copies (snapshots, backup copies) are opened with a normal connection (they
  are ours) or `immutable=1`, never `mode=ro`; `_mailbox_counts` reads a snapshot, so the kept mailbox is not touched.
  README states Python 3.9 to 3.14. The busy-timeout test's fixture is changed so it shows readers waiting for a held
  lock on every supported SQLite. `scripts/validate.sh` green on 3.9.6, 3.10.7 and 3.14.3, outputs recorded in the todo.
- **D52 deny rules stay while Claude sessions are open (R2-10; revised after the coordinator's review).** If any Claude
  Code session is alive (a `~/.claude/sessions/<pid>.json` whose pid is alive, read as `doctor` does) or a bridge server
  of this runtime runs, `uninstall-claude` removes the MCP entry, keeps the seven deny rules, and says why: close every
  Claude session and run it again from a terminal to remove them. Otherwise it behaves as today. Repeating the command
  is safe. Consequence, accepted: run from inside a Claude session it always keeps the rules — the caller is itself an
  open session, and in R2-10 the session that exposed the tools was the one running the uninstall. So the message
  gives the exact terminal command to copy and says "close every Claude Code session first, then run this in a
  terminal"; README §卸载 and the collaboration-ops skill make this step the user's, in a terminal, instead of an
  agent's. Codex is unaffected (only Claude has the deny rules).

## Requirements

1. D49: envelope text tested; the fallback tested with a fake host (idle, unregistered target → one re-send, then
   `registration-missing` if still unregistered); no `target-busy` hold for that case.
2. D50: order and refusal tested for the controller (create, continue, status, cancel, permissions) and `doctor`; a
   `node-too-old` refusal writes no envelope and starts no host process.
3. D51: migration, reinstall-around-history and doctor tested on a WAL-mode file with no `-wal`/`-shm`; full
   validate on the three Pythons.
4. D52 tested with a fake live session and a fake running server (each alone keeps the rules); README uninstall
   procedure updated.
5. Interface/checklist cross-references for R2-1, R2-6, R2-7, R2-9, R2-10; vendored bridge untouched unless a step
   needs it (then `UPSTREAM.md` and the manifest).

## Testing strategy

Python tests with fixture homes, fake `claude`/`node` binaries and WAL fixtures, as existing tests do. Live, in a
temporary `AGENT_RELAY_HOME` and HOME (coordinator told first): `doctor` and a controller create with nvm v12 first
in PATH (refusal before any write) and with the pinned node (success); migration and reinstall-after-uninstall with
`/usr/bin/python3`; `uninstall-claude` with a live session record. The R2-10 acceptance reproduces round 2 (all
bridges stopped, one Claude session open: rules kept and the session lists no worker tool; session closed, run again:
rules removed) — on real host files only with the user's agreement, otherwise by the coordinator. R2-6 needs real Claude targets: C3 Codex → Claude three
runs each on a plain repository and on a worktree, quick task, all results returned — run by or with the coordinator.

## Boundaries

- Always: refuse before touching a host; keep history; report numbers as measured.
- Ask first: the real `~/.agent-relay`, `~/.claude`, `~/.codex`; clearing envelopes e168ea and 269770 (out of scope,
  a follow-up action for the user).
- Never: edit `~/.codex/config.toml` for the user; push without approval.

## Out of scope

R2-3, R2-5, R2-8 (a later acceptance-kit module); R2-2, R2-4 (observations).

## Success criteria

1. All tests green on Python 3.9.6, 3.10.7 and 3.14.3.
2. Live checks above pass; the coordinator's C3 re-run returns every result.
3. README states the Python and Node ranges and the D52 behaviour.

## Open questions

None.
