# Spec: session-routing

## Objective

Make the extracted unified session routing agent-relay's own: the pure routing policy and public-outcome
validator (`hooks/session_routing.py`) and the `session-routing` skill. Claude↔Claude uses `ListAgents`/`SendMessage`,
Codex↔Codex uses the Codex App task/thread tools, Claude↔Codex uses the mailbox; fallback rules stay exactly as in
the baseline. The only change is the D1 rename of the public transport label for the mailbox route
(interface §9: "Transport label renamed with D1").

Readers: the user reviewing the split; agents building `cross-host-delegation`, which emits and validates the same
label.

Sources: [the interface document](../docs/collaboration-interface.md) §9; [the pre-split baseline](../docs/baselines/collaboration-pre-split.md)
items 2–6; the measured code below.

## Assumptions

Confirmed by the user on 2026-10-07:

1. **The label is the only Spec Guard name in routing.** Measured: `spec-guard-bridge` appears 4 times in
   `session_routing.py` and 4 times in the skill; nothing else in routing names Spec Guard.
2. **The label is not persisted.** The delegation database stores no transport or outcome (`authorizations`,
   `delegations` tables), and the mailbox stores message bodies, not routing outcomes, so renaming cannot break
   migrated state.
3. **One label, one owner.** `cross-host-delegation` imports `validate_public_outcome` from routing and emits the
   label in two places (`session_delegation_backend.py:31`, `session_delegation_control.py:298`). If routing renames
   alone, every delegation outcome fails validation. So routing owns the value as a constant and the two delegation
   emit sites import it in this module (decision D10).
4. **No behavior change.** Selector order, fallback conditions (authorization, ready bridge, unique join, at most once,
   never after an unknown native dispatch), the no-body rule, and the outcome schema version (1) are unchanged.

## Decisions

Taken as recommended by the user on 2026-10-07.

- **D10 label value and ownership.** `agent-relay-bridge` (keeps the "-bridge" shape the
  interface and skills already explain), defined once as `BRIDGE_TRANSPORT` in `session_routing.py`; the two
  delegation emit sites import it; skill text in `session-routing` and `session-delegation` uses the new value.
  This touches two lines of delegation code ahead of `cross-host-delegation`, because the alternative leaves
  delegation broken between the two modules.

## Requirements

1. `BRIDGE_TRANSPORT = "agent-relay-bridge"` in `session_routing.py`; `TRANSPORTS`, the selector return, the
   fallback route, and the bridge check use it; no string literal of the label remains in code.
2. `session_delegation_backend.py` and `session_delegation_control.py` import `BRIDGE_TRANSPORT` instead of the
   literal; no other delegation change.
3. Skill text: `skills/session-routing/SKILL.md` (4) and `skills/session-delegation/SKILL.md` (2) use the new
   value.
4. Interface §9 rows state the new value (current column keeps the baseline value as evidence, target column
   becomes "`agent-relay-bridge` (D1, D10)").
5. Tests: assertions pinning the old value move to the constant or the new value; none removed.
6. Old value rejected: a test asserts `validate_public_outcome` refuses `spec-guard-bridge`, so a stale emitter
   cannot pass silently.

## Commands

```bash
/bin/bash scripts/validate.sh
python3 -B plugins/agent-relay/hooks/session_routing.py --help
```

## Project structure

Changed only: `hooks/session_routing.py`, `hooks/session_delegation_backend.py` (import),
`hooks/session_delegation_control.py` (import), the two skills, the tests that pin the label,
`docs/collaboration-interface.md` §9, and `tasks/session-routing/`.

## Testing strategy

- `scripts/validate.sh` green; total 218 (217 + the old-value rejection test).
- Name scan: no `spec-guard-bridge` in `plugins/agent-relay/`; history and baseline docs keep it as evidence.
- Real-host comparison: checklist B1–B5 in the acceptance run after all translation modules.

## Boundaries

- Always: keep routing policy and outcome schema identical; one source for the label.
- Ask first: any other delegation change; changing the schema version.
- Never: copy message bodies into routing metadata; push the repository.

## Success criteria

1. Tests green (218); the old label is refused.
2. No old label left in plugin code, skills, or tests.
3. Interface §9 updated.

## Open questions

None; D10 is decided.
