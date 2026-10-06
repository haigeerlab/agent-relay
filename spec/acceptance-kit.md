# Spec: acceptance-kit

## Objective

Give agent-relay one way to run its tests and one shared real-host acceptance kit, so that every translation
module, every hardening module, and both integration rounds (brief phase 4) are judged the same way instead of
each writing its own checks. Also make the extracted tests stand alone: today 198 of 202 pass and 4 fail because
they read files that stayed in Spec Guard (Spec Guard `spec/collaboration-extraction.md`, decision D7).

Readers: agents building the later modules, and the user running or reviewing an acceptance round.

Sources: [the split brief](../docs/collaboration-split-brief.md) (phases 2 and 4), the real-host section of
[the pre-split baseline](../docs/baselines/collaboration-pre-split.md), and
[the interface document](../docs/collaboration-interface.md) (current and hardening-target columns).

## Assumptions

Confirmed by the user on 2026-10-07:

1. **Test entry.** `scripts/validate.sh` runs every test file under `plugins/agent-relay/hooks/` and exits non-zero
   on any failure. It replaces the extracted `test-collaboration-suite.sh`, which still names Spec Guard paths.
   No ShellCheck or other linters yet (packaging may add them).
2. **No behavior change.** Only test files, the runner, and new acceptance files change; no product code under
   `plugins/agent-relay/` other than tests.
3. **The kit is a checklist plus small helpers, not a robot.** Real-host acceptance needs Codex App threads that
   only the user can open, so it cannot be fully automated. The authority is one checklist; helpers only remove
   the operator setup errors the baseline hit (wrong `--tools`, permission prompts hanging background sessions,
   Codex auto-review not noticed).
4. **One checklist, two columns of expectations.** Each item states its expected result under the current column
   (round 1, translation) and under the hardening-target column (round 2); items that exist only after
   hardening are marked 【加固】 and skipped in round 1 (brief phase 4).
5. **Records are files in this repository** under `docs/acceptance/`, one per run, holding host versions, plugin
   source and commit, each item's steps, result, and evidence (message ids, not message bodies).
6. **Test identities** use the prefix `ar-acc-<run>-*` so cleanup can retire exactly them; message bodies of other
   identities are never read (baseline rule).

## Decisions

Taken as recommended by the user on 2026-10-07.

- **D8 the four standalone failures.**
  - `test_native_only_collaboration.py` (2): re-point the record paths to `docs/history/spec-guard/…` and the
    plugin paths to `plugins/agent-relay/…`; drop the two Spec Guard-only files it scans
    (`spec/ledger-dependency-lock.md`, `docs/optional-features.md`), which agent-relay does not have.
  - `test_skill_entrypoints.py::test_repository_validation_runs_the_entry_contract`: assert `scripts/validate.sh`
    runs the suite instead of Spec Guard's runner.
  - `test_skill_entrypoints.py::test_optional_feature_docs_explain_smooth_preapproval_and_limits`: it checks
    Spec Guard's `docs/optional-features.md`. Removed here and have `packaging` add the same four
    phrases as an assertion on agent-relay's README (the README does not exist yet). Net test count goes
    202 → 201 until `packaging`, recorded as an approved difference.

## Requirements

1. `scripts/validate.sh`: runs all `test_*.py` in `plugins/agent-relay/hooks/` with `python3 -B`, prints a per-file
   summary and a total, exits 1 on any failure; Bash 3.2 compatible. `test-collaboration-suite.sh` is removed.
2. The D8 test changes; after them `scripts/validate.sh` is green with 201 tests.
3. `docs/acceptance/checklist.md` with these sections, each item having an id, host pair, steps, expected
   (current / target), and evidence field:
   - A. Setup and preflight: host versions, plugin source and commit, approval modes, the session list the user
     must open (project × host), identity registration.
   - B. Messaging: Claude↔Claude, Codex↔Codex, Claude↔Codex both ways with direct replies; the same idle Claude
     woken twice; an unbound session is not woken; an auto-approved session cannot bind.
   - C. Delegation: create both directions, same-session second round, read-only negative, stop, exact mailbox
     result return, same-name short-id disambiguation.
   - D. Integration (brief 4.1–4.3): agent-relay alone in a project; Spec Guard plus agent-relay; cross-project
     pairs; artifact handoff by reference; 【加固】 fault items (unknown not replayed, expired not delivered,
     same retry key no duplicate).
   - E. Cleanup: retire test identities, remove test artifacts, confirm the guide plugin version unchanged.
   Every baseline item 1–10 and finding 1–7 maps to at least one checklist item.
4. `docs/acceptance/record-template.md`: the per-run record format.
5. `scripts/acceptance/preflight.sh`: read-only; prints Claude Code and Codex versions, the agent-relay plugin
   source and commit on each host (or "not installed"), Codex `approvals_reviewer`, and the exact background
   Claude launch command for a test identity (`--permission-mode dontAsk`, the mailbox tool allow list, no
   `--tools ""`). Writes nothing.
6. `scripts/acceptance/cleanup.sh <run>`: lists `ar-acc-<run>-*` identities and retires them only after an
   explicit `--confirm`; never touches other identities.

## Commands

```bash
/bin/bash scripts/validate.sh
/bin/bash scripts/acceptance/preflight.sh
/bin/bash scripts/acceptance/cleanup.sh <run>            # preview
/bin/bash scripts/acceptance/cleanup.sh <run> --confirm
```

## Project structure

- `scripts/validate.sh` — new test entry.
- `scripts/acceptance/{preflight,cleanup}.sh` — helpers.
- `docs/acceptance/checklist.md`, `docs/acceptance/record-template.md` — the kit.
- Changed: `plugins/agent-relay/hooks/test_native_only_collaboration.py`, `test_skill_entrypoints.py`; removed:
  `plugins/agent-relay/hooks/test-collaboration-suite.sh`.

## Testing strategy

- `scripts/validate.sh` green (201) and red when one test is broken on purpose.
- Helpers: a small test with fake `claude`/`codex` binaries for preflight output and for cleanup refusing without
  `--confirm` and touching only the run's prefix.
- Checklist coverage: a review table in todo.md mapping baseline items 1–10 and findings 1–7 to checklist ids.
- No real-host run in this module; the first one happens after all translation modules (brief phase 2).

## Boundaries

- Always: keep product code unchanged; keep the checklist the single authority for acceptance.
- Ask first: removing or weakening any test beyond D8; adding linters; any helper that writes host settings.
- Never: read other identities' message bodies; change host or project permissions; retire identities without
  `--confirm`.

## Success criteria

1. `scripts/validate.sh` passes with 201 tests; the only difference from the extracted suite is D8.
2. The checklist covers every baseline item and finding, with current and target expectations.
3. Preflight and cleanup behave as specified under their tests.

## Open questions

None; D8 is decided.
