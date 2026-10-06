# Acceptance record: <run id> (<date>)

Copy to `docs/acceptance/<date>-<run>.md`. One row per checklist item; write "skipped (round 1)" for 【加固】
items in round 1 and "not run" with a reason for anything else not exercised.

## Run

| Field | Value |
|---|---|
| Purpose | translation / hardening module `<id>` / integration round 1 / integration round 2 |
| Expectations | current column / hardening-target column |
| agent-relay commit | |
| Spec Guard commit (if installed) | |
| Claude Code version | |
| Codex version (CLI and App) | |
| Plugin sources | (preflight output) |
| Codex `approvals_reviewer` and App selector | before → during → after |
| Sessions opened by the user | project × host list (A3) |
| Permission changes made for the run | each change, who made it, reverted in E3 |

## Preflight output

```
<paste scripts/acceptance/preflight.sh output>
```

## Results

| Id | Host pair / project | Steps taken | Result (pass / fail / partial / skipped / not run) | Evidence (message ids, states, exit codes, screenshots) |
|---|---|---|---|---|
| A1 | | | | |

## Findings

Numbered; each says whether it is product behavior or an operator setup error, and which module owns it.

## Cleanup

E1–E5 results, including the retired identities and the guide plugin versions after the run.
