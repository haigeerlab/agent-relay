# Spec: orchestrator-removal

## Objective

agent-relay promises a same-Mac mailbox with exactly ten MCP tools (`docs/collaboration-interface.md` §2.1, interface
1.0–1.3). The vendored bridge still registers seventeen: the ten mailbox tools plus `bridge_retire` and six Codex
orchestration tools (`ask_codex`, `review_with_codex`, `bridge_orchestrate_codex`, `bridge_continue_codex`,
`bridge_orchestration_wait`, `bridge_orchestration_status`). The boundary holds only because the hosts filter tools
(`DENIED_TOOLS`, Claude deny rules, Codex `enabled_tools`). Found by the 0.4.0 architecture review (2026-10-08, A1, A8,
A9; the orchestrator also carries known bugs B1–B3).

The orchestrator overlaps the delegate plugin, which the user made the only way to hand work to Codex (2026-10-08), and
is denied on every host, so no run exists in production. The user first chose to split it into its own plugin, then,
after the round-2 coordinator pointed out that overlap, chose to **delete** it (2026-10-08). History stays in git; tag
`v0.4.0` has the last copy.

After this module the bridge registers exactly the ten mailbox tools and the runtime probe enforces that set.

Readers: the user; the round-2 coordinator, who re-checks on the real host when 0.5.0 is released.

## What exists today (main 180de7b, 2026-10-08)

- `bridge/src/server.ts:23,26,63,70,134,504-661`: imports `Orchestrator` and `simple-tools`, a "Codex workers" paragraph
  in the server instructions, builds the orchestrator and hands it to `Housekeeper`, registers `bridge_retire` (504) and
  the six orchestration tools (531-661).
- Only the orchestrator uses `simple-tools.ts` and `process-info.ts`. `lifecycle.ts` (`retireAgent`) is also used by
  the CLI `retire`, which `native_collaboration_retire.py` runs.
- `bridge-store.ts:72-116,294,893-1060,1106`: the run types, nine run methods (`createRun`, `getRun`, `updateRun`,
  `runsWithStatus`, `undeliveredRuns`, `claimRunDelivery`, `adoptRun`, `appendRunEvent`, `runEvents`) and the run count
  in the diagnostic report.
- `housekeeping.ts:57,63,72,87,95`: reconciles runs every third tick and prunes run files.
- `diagnostics.ts:118`; `cli.ts:32-33,66,459,482-483,514-515,669`: `resolveCodexBinary` import, `REQUIRED_TOOLS` with
  `ask_codex` and `bridge_orchestration_wait`, the runs directory in the permission sweep, doctor's "Codex runs",
  `status`'s runs line and help text. `paths.ts:27-33`: `runsDir`, `worktreeRoot`.
- `schema.ts:56-80,118,126,136`: the two orchestration tables are created by the v1 baseline migration and touched by
  v2/v3. Schema version 5.
- Python: `native_collaboration_runtime.py:255-266` `MAILBOX_TOOLS` (10) and `DENIED_TOOLS` (7);
  `native_collaboration_adapters.py:22,59-154` writes Claude deny rules for the seven; doctor and the Codex
  approval-table code read both lists.
- Text naming the removed tools: server instructions, `bridge/README.md`, `bridge/INSTRUCTIONS.md`,
  `bridge/CHANGELOG.md`, `docs/collaboration-interface.md`, `skills/session-delegation/SKILL.md`, tests.
- Bridge files are checked against `bridge/UPSTREAM.sha256`; every change updates the manifest and the `UPSTREAM.md` row.

## Assumptions (accepted by the user 2026-10-08)

1. Deleted: `orchestrator.ts`, `simple-tools.ts`, `process-info.ts`; the run types and methods in `BridgeStore`;
   `orchestration.test.ts`, `simple-tools.test.ts`; `scripts/smoke-orchestrator.ts`;
   `docs/AUTONOMOUS-ORCHESTRATOR-DESIGN.md`; the `bridge_retire` MCP tool (`lifecycle.ts` and CLI `retire` stay).
2. Follow-on edits: `Housekeeper` without reconcile and run-file pruning; `diagnostics` without run counts; in the TS CLI
   only what names the orchestrator (`REQUIRED_TOOLS`, doctor "Codex runs", `status` runs line, `runsDir` use, help);
   `paths.ts` without `runsDir` / `worktreeRoot`. The wider TS CLI cleanup is its own later module.
3. Untouched: the schema and both orchestration tables; a leftover `runs/` directory on disk (no production runs;
   `uninstall --purge` removes the data directory anyway).
4. Hosts: the probe requires the exact ten; `DENIED_TOOLS` becomes `LEGACY_WORKER_TOOLS`, used only to recognise and
   remove Claude deny rules and Codex approval sub-tables on uninstall; new installs write no deny rules for them; an
   upgraded host keeps its old rules until uninstall.
5. Must check and fix every mention of the removed tools, "Codex workers" or `bridge_retire`: server instructions,
   collab and session-delegation skills, bridge README / INSTRUCTIONS, `docs/collaboration-interface.md`.
6. Interface stays 1.3 (§2.1 already lists exactly these ten). The "This document defines interface `1.0`" drift at
   `collaboration-interface.md:27` is not fixed here.
7. `UPSTREAM.md` records what was removed and that tag `v0.4.0` holds it; manifest updated.
8. Red first: MCP tools exactly ten; probe refuses an eleventh tool and a missing one. Then a live upgrade from v0.4.0
   and uninstall in a temporary HOME.

## Decisions

- **D90 delete, do not split.** Supersedes the withdrawn `orchestrator-split` draft (never committed). No new package,
  no CLI `send`, no new public entry point.
- **D91 the tool set is the server's job.** `server.ts` registers the ten mailbox tools and nothing else; the probe
  compares `tools/list` with `MAILBOX_TOOLS` for equality. Host filtering stays as a second layer only for hosts
  installed before this version.
- **D92 legacy names for cleanup only.** `LEGACY_WORKER_TOOLS` (the seven names) is read by uninstall and the Codex
  approval-table cleanup, never by install or the probe. Doctor stops expecting deny rules for them; a host that still
  has them is not reported as wrong.
- **D93 dormant tables.** The orchestration tables stay in the schema and in existing mailboxes, unread. A schema test
  opens a v5 mailbox holding orchestration rows and finds them intact.
- **D94 docs.** Every place in assumption 5, `UPSTREAM.md`, CHANGELOG `[Unreleased]`. The interface document's
  "Upstream worker and orchestration tools stay disabled" becomes "were removed in 0.5.0 (tag `v0.4.0` has them)".

## Requirements

0. Red first: `mcp-integration.test.ts` lists the tools and expects exactly the ten; a Python probe test fails on an
   eleventh tool and on a missing one.
1. Bridge: the deletions and edits of assumptions 1–2; `npm run check` green; no source file imports a removed module
   (`grep` in the check task); a schema test per D93.
2. Python tests: probe equality; install writes no deny rules for the legacy names; uninstall of a Claude config with
   the old deny rules and of a Codex config with their approval sub-tables removes all of them; doctor is ok on a fresh
   install and on a host that still has the old rules.
3. Live check in a `mktemp -d` HOME: install the v0.4.0 runtime and hosts, write messages, acknowledgements and an
   orchestration row; upgrade to this branch; schema 5, every row intact, `doctor` all ok, `tools/list` the ten;
   uninstall removes the old deny rules and approval sub-tables. Temporary HOME to the Trash.
4. Validation: `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green on all jobs.

## Boundaries

- Always: the sealed state root in every test; manifest and `UPSTREAM.md` updated with every bridge change.
- Ask first: the real `~/.agent-relay`, `~/.claude`, `~/.codex`; any schema change; anything beyond assumption 2 in the
  TS CLI.
- Never: drop or rewrite the orchestration tables; delete a user's `runs/` directory; push without approval.

## Success criteria

The bridge lists exactly ten tools and the probe enforces it; no orchestrator code remains outside git history; a host
installed by 0.4.0 upgrades with its data intact and uninstalls cleanly.

## Open questions

None. Accepted by the user on 2026-10-08: assumptions 1–8, D90–D94.
