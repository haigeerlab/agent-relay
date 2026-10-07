# Plan: acceptance-kit-round2

Based on [`spec/acceptance-kit-round2.md`](../../spec/acceptance-kit-round2.md) (accepted by the user on 2026-10-07:
assumptions 1–5, D53–D57; D57 added for R2-12 on 2026-10-08). Branch `claude/acceptance-kit-fixes` from main fc7ee7e. No bridge change. Red → green
each task; preflight stays read only; tests drive it with fixture homes and fake `claude`/`codex` CLIs, as
`test_acceptance_helpers.py` does now.

## Task List

### Task 1: Probe what `${CLAUDE_PLUGIN_ROOT}` names for a `directory` marketplace (D53, open question)
A throwaway plugin in the scratchpad (one skill whose text is `ROOT=${CLAUDE_PLUGIN_ROOT}` and a marker file), served
by a throwaway `directory` marketplace, installed at local scope for a throwaway scratch project; one
`claude -p` run there loads the skill and reports the substituted path; then change the source's marker and run
again (does the session see the source or a copy made at install?). Uninstall plugin and marketplace afterwards;
snapshot `installed_plugins.json` / `known_marketplaces.json` before and after. Writes the host's plugin records,
so it runs only after the user agrees (asked when this task starts). Outcome decides whether D53's tree-hash refusal
is needed. **Files:** none in the repo; result recorded in the todo.

### Checkpoint (gate): Task 1 result and the D53 variant, reported to the user

### Task 2: Tree hash and stale copies in preflight (D54)
Move preflight's Python into `scripts/acceptance/preflight.py` (the `.sh` stays the entry) so helpers are testable.
`tree_hash(root)`: sha256 over sorted relative paths and file bytes, ignoring `node_modules`, `.git`, `__pycache__`,
Codex `migrated-command-skills`. preflight prints the source hash and, per copy, `current` or `STALE` with the refresh
command: Claude — each install record's `installPath` (labelled "record"); Codex — each directory under its cache.
Tests: equal trees, changed file, ignored entries, missing copy.
**Files:** `scripts/acceptance/preflight.sh`, new `preflight.py`, `hooks/test_acceptance_helpers.py`.

### Task 3: Allow lists, `--design`, launch line (D55, D56)
`base` and `routing` lists; routing adds `Bash(python3 -B <root>/hooks/session_routing.py select *)` and, with
`--design <path>`, `Read(//<abs path>/**)` (a note when absent). Launch line
`claude "<prompt>" --bg --permission-mode dontAsk --allowedTools "<list>"` plus "the prompt must come first". Exact
strings tested.
**Files:** `preflight.py`, tests.

### Task 4: One root-resolution block in the three skills (D53)
The block decided at the Task 1 gate, identical in `collaboration-ops`, `session-delegation`, `session-routing`;
a test pins it in all three and forbids `installed_plugins.json` / `plugins/cache` in skill text.
**Files:** three `SKILL.md`, `hooks/test_skill_entrypoints.py` (or a new test).

### Task 4b: One node and one read for install, upgrade, retire and cleanup (D57, R2-12)
`install`/`upgrade`/reinstall and `retire` select the node with `select_node` (refusing below 22.5.0 before any build
or retire); npm runs with `PATH=<chosen node dir>:$PATH` and `--npm` defaults to the npm beside the chosen node.
`cleanup.sh` uses `open_mailbox_read_only`. Tests: fake v12 `node` first on PATH plus fake v24 node/npm (the fake npm
records which `node` its env resolves); retire default; cleanup on a closed WAL mailbox under `/usr/bin/python3`.
**Files:** `hooks/native_collaboration_runtime.py`, `hooks/native_collaboration_retire.py`,
`scripts/acceptance/cleanup.sh`, tests.

### Task 5: Docs
Checklist A4 (launch line, base list), D8 (routing list), D9 (routing list with `--design`), A1 (STALE copies must
be refreshed before the run); interface rows if any name the root resolution; README acceptance pointer if present.

### Task 6: Live (read only, plus a temporary home for D57)
In a temporary HOME/`AGENT_RELAY_HOME` with nvm v12 first in PATH and `/usr/bin/python3`: reinstall around kept
history, retire a test identity, `cleanup.sh` preview/confirm on a temporary run. Then preflight on this Mac with `--design ~/Documents/haigeerlab/design-test`: every copy's status, the two lists, the
launch line; compare with the coordinator's R2-11 observation. Nothing written (host files' mtime and hash checked).

### Checkpoint (gate): module review
