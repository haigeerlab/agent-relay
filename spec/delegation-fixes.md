# Spec: delegation-fixes

## Objective

Fix the delegation defects that the baseline recorded and the translation kept, plus one round 1 found:

- **Finding 3.** A create that the host holds on a prerequisite leaves a named record that never launched. The
  name then stays ambiguous for every later create, and cancelling the record answers `unknown`.
- **Finding 4.** A second round (`continue`) to an idle Claude target answers `held`/`target-busy` while
  `hostStatus=idle`.
- **Round 1 finding 7.** Creating a Claude target on Claude Code 2.1.291 answers `state=unknown` although the
  session starts and returns its result; every later `continue` then refuses with
  `delegation-is-not-ready-for-follow-up`. On 2.1.291 this hides finding 4, so it is fixed first. The Task 4
  capture showed the cause is not timing but the host's `--cwd` filter (below, D19).

Done means checklist C3 and C7 meet their target column: the second round passes both ways, and a held create
leaves nothing that blocks or confuses a later create with the same name.

Readers: the user reviewing the fix; the agent building it; the round-2 acceptance run.

Sources: [round 1 record](../docs/acceptance/2026-10-07-round1.md) row D10/C1–C5 and finding 7; [baseline](../docs/baselines/collaboration-pre-split.md) item 9 and findings 3–4;
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

**Finding 7, as measured in Task 4 (Claude Code 2.1.291, 2026-10-07).** A background session started in a
plain repository is listed on the first poll after `--bg` returns, with or without `--cwd`. One started in a
**git worktree** is listed at once without a filter, with `cwd` = the worktree path, but `claude agents --json
--all --cwd <worktree>` never lists it (60 s); `--cwd <main checkout>` does. Round 1's Claude target was a
spec-guard worktree. The adapter always passes `--cwd <project>` (`claude.py` `_sessions`), so in a worktree it
never sees its own session, however long it waits.

**Finding 7, as first read from the code.** `create` parses the background id from the host's stdout and calls `_bind_observed`
(`claude.py:441-457`), which looks the entry up through `_settled_session` three times within 0.7 s. On 2.1.291
the entry appears later, so the row gets `host_ref` but no `host_session_ref` and goes `unknown`
(`record_host_unknown`). Nothing looks again: `status()` compares the entry's session id with the stored `None`
and answers `hostStatus=unknown`, and `continue_turn` refuses any row that is not `completed` with both refs. The
store already allows the repair: `bind_host` accepts `unknown → created` when the refs it adds do not conflict
(`session_delegation.py:702-741`).

## Assumptions

1. **Finding 4's cause is the rule mismatch above.** Task 4 saw only `(done, idle)` after a turn (process still
   alive) and `(working, busy)` during one, which the current reconcile handles; `active`/`blocked` with `idle`
   was not seen for a one-shot session and is expected for a delegated session that stays registered. Originally
   assumed: most likely `claude agents --json --all` reporting an idle
   background session after its first turn as `state=active` (or `working`) with `status=idle` on Claude 2.1.288+.
   This is inferred from code and the recorded output, not yet seen in raw host JSON. The capture task records the raw
   entry before any change; if it shows something else, the fix follows the evidence and this spec is updated
   first.
2. **No Codex-side code change is expected;** Claude → Codex round two passed in the baseline (item 7) and round 1
   (D10). It is still rerun live, because C3 is judged both ways.
3. **The record schema stays** (`user_version = 2`, same tables and columns, same state enum and evidence words).
   The fixes change transitions the code takes and how rows are selected, not what is stored.
4. **Build after round 1.** Round 1 passed on 2026-10-07 (verdict in its record, release 0.1.0); code starts now.
5. **Live checks are run by the agent** (user, 2026-10-07): the capture and the final C3/C7 check start a
   background Claude session in a throwaway scratchpad project. Temporary allow rules stay inside that project and
   are removed afterwards.

## Decisions

D15–D17 taken as recommended by the user on 2026-10-07; D18 added by the project owner after round 1.

- **D15 held create (revised by the project owner at Task 1).** Name lookup prefers launched rows: when a friendly
  name matches at least one row that reached a host (`host_ref` set), rows that never did are left out; when every
  match is never-launched, they are matched as today. The held row itself is not changed, so the designed retry —
  the same idempotency and launch keys reach the same `creating` claim (`test_held_prerequisite_can_retry_the_same_
  claim_without_consuming_capacity`) — keeps working. `list` still shows every row; a leftover never-launched row
  is reachable with `--disambiguator` and cancels cleanly (D16).
  *Why revised:* the first D15 (move a held row to `cancelled` at once) would also cancel its authorization and so
  break that retry. Finding 3 arises because the skill makes a fresh create, after the user fixes the
  prerequisite, with new keys (keys are reused only after a lost response); the new rule removes the ambiguity that
  this creates without changing either path.
- **D16 cancelling a never-launched row.** `cancel` on a row with no host reference (legacy rows such as
  `27f0de`, or any row left `creating` by a crash) moves it to `cancelled` and answers `cancelled`, because no host
  exists to confirm. This narrows the skill's rule "only show cancelled after the host confirms" to rows that
  reached a host; the skill text says so.
- **D17 Claude idle rule.** One predicate decides "the Claude target is idle" and both `_reconcile_lifecycle` and
  `continue_turn` use it, built from the raw states the capture task records. A state the predicate does not know stays
  busy (safe default), and the answer names it so the next mismatch is diagnosable.

- **D18 late Claude entry (revised after the round 1 owner's acceptance note).** Two layers:
  1. *At create,* `_settled_session` keeps looking for the background entry with backoff up to a bounded total
     (default 10 s; the exact bound is set from the Task 4 capture, at least twice the observed delay). Found and
     valid → `created`, as on 2.1.288. Not found within the bound → the answer is `state=unknown`,
     `hostStatus=unknown`, `prerequisite=host-entry-pending`, and the row keeps `host_ref` with no session.
  2. *On the next `status` or `continue`,* a row that is `unknown` with a `host_ref` and no `host_session_ref` is
     looked up again by `host_ref`; if it passes the create checks (session id is a UUID prefixed by `host_ref`,
     cwd is the project, kind background) it is bound with `bind_host` (`unknown → created`) and handled as a
     `created` row.
  *Failure* is: the entry is still absent on a later call (answer stays `unknown`, `host-entry-pending`), or it
  appears with a different session prefix, cwd or kind (answer `unknown`, nothing bound, `host-entry-invalid`).
  Such a row is cancelled with the normal stop path, because `host_ref` is known.
  *Regression sample:* round 1's row (`host_ref` 244e528e, no session ref, `unknown`) — its shape, not its prompt.

- **D19 list without the host's cwd filter (project owner, after Task 4).** `_sessions` runs
  `claude agents --json --all` without `--cwd` and keeps relying on `_exact_session`'s exact checks (id, session id
  prefixed by the id, cwd equal to the resolved project, kind background), which already reject any other
  session. This is the fix for finding 7; D18 stays as a bounded safety net and as the repair for rows already
  stuck (round 1's row), not as the cause's remedy.

- **D16 narrowed (after the live C7 run, 2026-10-07; user decision).** Live C7 (controller 745ac90, Claude origin,
  Claude target in design-test): the second create answered `unknown` with no `host_ref` while the host session
  `ar-acc-r1fix-c7-501157b7` ran (`blocked`, `idle`), and D16 then answered `cancelled` without stopping it —
  **unsafe**. Fix:
  - Only a row still `creating` (no launch attempted, or the host refused before starting) cancels without a
    host. An `unknown` row without `host_ref` answers `unknown` with `prerequisite=host-ref-missing` on `cancel`,
    `status` and `continue`; its authority is frozen by cancel, nothing is stopped or looked up. The user stops the
    host session by hand (`claude agents` shows it as `<friendly name>-<8 hex>`, starting with the short id).
  - *Rejected (user):* finding the session by its internal name (`<friendly>-<id8>`, cwd, kind) and stopping it
    — it would relax the rule that a session is never found by title, project or short id.
  - The `--bg` parser accepts any `backgrounded · <id8>` line, whatever follows the id; one such line was seen
    today (`backgrounded · <id> (idle — send a prompt to start)`) and the old regex rejected it. The exact line of
    the C7 run was not recorded, so this is the likely, not the proven, source of the missing `host_ref`.
  - *Cause proven by the C7c diagnostic (590b2c5):* launched from a background Claude session, `claude --bg` colors
    its output — `backgrounded · \x1b[36m<id>\x1b[39m · <name>` — so the id was never matched (rc 0, Claude 2.1.291,
    no timeout). Fix: strip CSI/OSC escape sequences before parsing `--bg` and `stop` output, and run host commands
    with `NO_COLOR=1` (and without `FORCE_COLOR`) as a second guard. This is the second half of round 1 finding 7
    for a Claude origin (the first half, a Claude target in a git worktree, is D19).
  - *D15 restated:* "never launched" = no `host_ref` and state `creating` or `cancelled`; an `unknown` row counts as
    launched for name lookup.

## Requirements

1. A create held on a prerequisite answers `held` with the prerequisite, as today, and can still be retried with
   the same keys.
2. After a held create named N, a create named N succeeds without `session-name-ambiguous`; `status`, `continue`
   and `cancel` on N reach the new session without `--disambiguator`.
3. `cancel` on a row still `creating` answers `cancelled` without a host; an `unknown` row without `host_ref`
   answers `unknown`/`host-ref-missing` and is never reported `cancelled`; launched rows behave as today.
4. `continue` to a Claude target whose raw entry matches the captured idle entry proceeds (native wake or resume)
   instead of `target-busy`. A target that is genuinely working still answers `target-busy`.
5. A Claude target in a git worktree is found at create (`created`), and by `status`, although
   `agents --cwd <worktree>` would not list it.
6. A Claude create whose entry appears within the bound answers `created` at once. One whose entry appears only
   after the create call returns answers `unknown`/`host-entry-pending`; the next `status` answers `created` (or
   later states) with the session bound, and `continue` works from there. A row whose entry never appears stays
   `unknown`/`host-entry-pending`; one with a different session prefix, cwd or kind stays `unknown`/
   `host-entry-invalid` with nothing bound.
7. Interface §10 rows "Held create" and "Claude round two" (and a row for finding 7) move to "done in `delegation-fixes`"; checklist C3 and
   C7 current columns updated; the `session-delegation` skill states D16.
8. No change to records already on disk is required; migrated legacy rows are handled by D16 at cancel time.

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
  cancel; Claude `status`/`continue` after a late entry; Claude `continue` against the captured idle entry), then
  the fix turns it green.
- Regression: a busy capture still gives `target-busy`; a launched row's cancel still needs host confirmation;
  existing ambiguity between two launched sessions with the same name is unchanged (C6).
- Mutation: restoring the old reconcile rule turns the round-two test red; removing the `_resolve` filter turns the
  same-name test red.
- `scripts/validate.sh` green: 238 plus the new tests.
- Live: after the code, rerun C3 (both directions) and C7 with acceptance-kit in design-test and record it.

## Boundaries

- Always: reproduce before fixing; keep the schema; keep the public JSON fields.
- Ask first: permission changes outside the throwaway project; any schema or evidence-word change; touching findings other
  than 3 and 4.
- Never: delete delegation rows; change state-migration's acknowledgment rule; push the repository.

## Success criteria

1. The two Prove-It tests fail before and pass after; regression and mutation checks hold.
2. Live C3 in both directions (user premise 4, 2026-10-07), judged by the interface's hardening-target column:
   Codex → Claude create answers `created` or reaches it on the next `status`, and round two passes both ways; live C7 leaves no ambiguity and no `unknown` cancel.
3. Interface, checklist and skill updated as in requirement 7.

## Open questions

None; D15–D19 are decided, D16 narrowed after live C7.
