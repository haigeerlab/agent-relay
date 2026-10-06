# Spec: delegation-fixes

## Objective

Fix the two delegation defects that the baseline recorded and the translation kept:

- **Finding 3.** A create that the host holds on a prerequisite leaves a named record that never launched. The
  name then stays ambiguous for every later create, and cancelling the record answers `unknown`.
- **Finding 4.** A second round (`continue`) to an idle Claude target answers `held`/`target-busy` while
  `hostStatus=idle`.

Done means checklist C3 and C7 meet their target column: the second round passes both ways, and a held create
leaves nothing that blocks or confuses a later create with the same name.

Readers: the user reviewing the fix; the agent building it; the round-2 acceptance run.

Sources: [baseline](../docs/baselines/collaboration-pre-split.md) item 9 and findings 3–4;
[interface](../docs/collaboration-interface.md) §10 rows "Held create" and "Claude round two"; checklist C3, C7;
[cross-host-delegation](cross-host-delegation.md) assumption 3.

## What the code does today (measured)

**Finding 3.** `authorize_and_create` (`session_delegation_control.py:337-385`) writes the authorization and a
`creating` delegation row before it calls the adapter. When the adapter answers `held`
(`session_delegation_claude.py:483, 514`; the Codex adapter has the same shape) nothing moves the row: it stays
`creating` with no host reference. `_resolve` (`control.py:387-416`) matches every row by friendly name, so the
dead row joins every later lookup of that name. `cancel` on both adapters cancels the authorization and then, with
no host reference, returns `unknown` without moving the row (`claude.py:697-699`, `codex.py:827-831`). The row
stays `creating` for ever; `state-migration` later had to ask the user to acknowledge exactly this row (`27f0de`).

**Finding 4.** `continue_turn` (`claude.py:557-569`) first asks `status()` when the row is `created` or `running`.
`_reconcile_lifecycle` (`claude.py:520-555`) moves `running` to `completed` only when the host `status` is idle
**and** the host `state` is not `working` or `active`. If it is not completed and no prerequisite was set,
`continue_turn` answers `held` with `target-busy` and passes the host status through, which is exactly the baseline
output (`target-busy` with `hostStatus=idle`). A few lines later the same method treats `status=idle` with
`state` in `blocked`, `done`, `running`, `active` as idle enough to wake natively (`claude.py:592-593`). The two
rules disagree about `idle` + `active`.

## Assumptions

1. **Finding 4's cause is the rule mismatch above,** most likely `claude agents --json --all` reporting an idle
   background session after its first turn as `state=active` (or `working`) with `status=idle` on Claude 2.1.288+.
   This is inferred from code and the recorded output, not yet seen in raw host JSON. The capture task records the raw
   entry before any change; if it shows something else, the fix follows the evidence and this spec is updated
   first.
2. **Codex round two is out of scope;** it passed in the baseline (item 7).
3. **The record schema stays** (`user_version = 2`, same tables and columns, same state enum and evidence words).
   The fixes change transitions the code takes and how rows are selected, not what is stored.
4. **Build waits for round 1.** The map places this module after round 1 passes; round 1 still records C3 and C7
   against the current column. The spec and plan can be written now; code changes start after round 1 closes.
5. **Live checks are run by the agent** (user, 2026-10-07): the capture and the final C3/C7 check start a
   background Claude session in a throwaway scratchpad project. Temporary allow rules stay inside that project and
   are removed afterwards.

## Decisions

All three taken as recommended by the user on 2026-10-07.

- **D15 held create.** When the adapter answers `held` and no host reference was bound, the controller moves the
  row `creating → cancelled` (existing transition and evidence `host-cancelled`) and cancels its authorization,
  in the same call. The public answer stays `state=held` with the prerequisite named, as today. Name resolution
  (`_resolve`) skips rows that are `cancelled` and never got a host reference, so a later create with the same
  name is unambiguous. The row is kept for audit, not deleted.
  *Alternative rejected:* reusing the held row on the next create — the next create has a new launch key, prompt
  and possibly authority, so reuse would mix two authorizations.
- **D16 cancelling a never-launched row.** `cancel` on a row with no host reference (legacy rows such as
  `27f0de`, or any row left `creating` by a crash) moves it to `cancelled` and answers `cancelled`, because no host
  exists to confirm. This narrows the skill's rule "only show cancelled after the host confirms" to rows that
  reached a host; the skill text says so.
- **D17 Claude idle rule.** One predicate decides "the Claude target is idle" and both `_reconcile_lifecycle` and
  `continue_turn` use it, built from the raw states the capture task records. A state the predicate does not know stays
  busy (safe default), and the answer names it so the next mismatch is diagnosable.

## Requirements

1. A create held on a prerequisite leaves its row `cancelled`, its authorization `cancelled`, and its public
   answer `held` with the prerequisite.
2. After a held create named N, a create named N succeeds without `session-name-ambiguous`; `status`, `continue`
   and `cancel` on N reach the new session without `--disambiguator`.
3. `cancel` on a never-launched row answers `cancelled` and moves the row to `cancelled`; on a launched row it
   behaves as today.
4. `continue` to a Claude target whose raw entry matches the captured idle entry proceeds (native wake or resume)
   instead of `target-busy`. A target that is genuinely working still answers `target-busy`.
5. Interface §10 rows "Held create" and "Claude round two" move to "done in `delegation-fixes`"; checklist C3 and
   C7 current columns updated; the `session-delegation` skill states D16.
6. No change to records already on disk is required; migrated legacy rows are handled by D16 at cancel time.

## Commands

```bash
/bin/bash scripts/validate.sh
python3 -B plugins/agent-relay/hooks/session_delegation_control.py --help
claude agents --json --all --cwd <throwaway project>   # capture, read-only, after a user-approved launch
```

## Project structure

Changed only: `plugins/agent-relay/hooks/session_delegation{_control,_claude,_codex}.py` (and
`session_delegation.py` only if `_resolve` needs a store query), their tests, `skills/session-delegation/SKILL.md`,
`docs/collaboration-interface.md` §10, `docs/acceptance/checklist.md` C3/C7, and `tasks/delegation-fixes/`.
The raw host capture is stored as a test fixture, with ids replaced.

## Testing strategy

- Prove-It per finding: a failing test reproduces each defect first (held create then same-name create and
  cancel; Claude `continue` against the captured idle entry), then the fix turns it green.
- Regression: a busy capture still gives `target-busy`; a launched row's cancel still needs host confirmation;
  existing ambiguity between two launched sessions with the same name is unchanged (C6).
- Mutation: restoring the old reconcile rule turns the round-two test red; removing the `_resolve` filter turns the
  same-name test red.
- `scripts/validate.sh` green: 238 plus the new tests.
- Live: after the code, rerun C3 (Codex → Claude) and C7 once in a throwaway project and record it.

## Boundaries

- Always: reproduce before fixing; keep the schema; keep the public JSON fields.
- Ask first: permission changes outside the throwaway project; any schema or evidence-word change; touching findings other
  than 3 and 4.
- Never: delete delegation rows; change state-migration's acknowledgment rule; push the repository.

## Success criteria

1. The two Prove-It tests fail before and pass after; regression and mutation checks hold.
2. Live C3 Codex → Claude round two passes; live C7 leaves no ambiguity and no `unknown` cancel.
3. Interface, checklist and skill updated as in requirement 5.

## Open questions

None; D15–D17 are decided.
