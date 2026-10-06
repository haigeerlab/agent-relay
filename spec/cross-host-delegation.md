# Spec: cross-host-delegation

## Objective

Make the extracted cross-host session delegation agent-relay's own: the controller and its Claude Code and Codex
backends (`hooks/session_delegation{,_backend,_claude,_codex,_control}.py`) and the `session-delegation` skill.
Permission intents, authority modes, lifecycle (create, continue, status, cancel), exact result return, and
same-name disambiguation stay as in the baseline, including the baseline's known defects (findings 2–4), which
`ops-commands` and `delegation-fixes` own. The change is the D1 renaming of every Spec Guard name the delegation
code still carries, plus the D9 state root.

Readers: the user reviewing the split; agents building `packaging`, `state-migration`, and `delegation-fixes`.

Sources: [the interface document](../docs/collaboration-interface.md) §10, §13; [the pre-split baseline](../docs/baselines/collaboration-pre-split.md)
items 7–9 and findings 2–4; the measured names below.

## Assumptions

Confirmed by the user on 2026-10-07:

1. **Measured names to rename (code):**
   - state root `~/.spec-guard/session-delegation` (`session_delegation_control.py:508`);
   - result route key prefix `spec-guard-result:` (`backend.py:70`, `control.py:218`) and idempotency prefix
     `spec-guard-result-send:` (`control.py:225`);
   - prompt tags `<spec-guard-result-route>` (`control.py:238-242`) and `<spec-guard-control>`
     (`claude.py:248-253`, `codex.py:610-614`);
   - Codex private MCP server `spec_guard_delegation` (`codex.py:24`) and its client/service name and title
     `spec_guard_session_delegation` / "Spec Guard Session Delegation" (`codex.py:437-438, 699`).
   Tests that pin these (15 assertions across four test files) move with them; none is removed.
2. **The server name and transport label are already done** (`mailbox-core`, `session-routing`); the test that
   passes the old server name as a parameter (`test_session_delegation_claude.py:140-155`) is updated here.
3. **Behavior is unchanged,** including findings 2 (`--expires-at` integer only), 3 (held create leaves a named
   envelope), and 4 (Claude second round `target-busy` while idle). They are recorded, not fixed.
4. **Delegation records keep their schema** (`authorizations`, `delegations`, `user_version = 2`); only their
   location changes. Moving existing records is `state-migration`.
5. **Verification is unit tests.** Real delegation (checklist C1–C8) runs in the acceptance after all translation
   modules; nothing here launches a host session.

## Decisions

Both taken as recommended by the user on 2026-10-07.

- **D11 new names,** one-for-one:
  `~/.agent-relay/delegation` (D9); `agent-relay-result:`; `agent-relay-result-send:`;
  `<agent-relay-result-route>`; `<agent-relay-control>`; Codex private server `agent_relay_delegation`;
  service name `agent_relay_session_delegation`, title "agent-relay Session Delegation".
- **D12 in-flight delegations across the rename.** A delegated session started under Spec Guard returns its result
  with a `spec-guard-result:` key, which the renamed controller will not recognise. The controller
  accepts only the new prefix, and `state-migration` refuses to migrate while any delegation is non-terminal
  (created/held/running), telling the user to finish or cancel it first under Spec Guard. This keeps one key format
  and puts the guard where the crossing happens.

## Requirements

1. All names in assumption 1 replaced per D11; no Spec Guard name remains in the delegation code or skill.
2. `default_state_root()` returns `~/.agent-relay/delegation`; the parent `~/.agent-relay` is created owner-only
   when absent (same as the runtime, D9) and the delegation directory keeps its current mode rules.
3. A test asserts the old result-key prefix is refused (`result-route-invalid`), so a stale key cannot pass.
4. Interface §10 and §13: delegation rows name the new markers and root; the D12 rule is added to §13's migration
   row as a precondition for `state-migration`.
5. Test count: 218 + 1 (old-prefix refusal) + at most one for the default root.

## Commands

```bash
/bin/bash scripts/validate.sh
python3 -B plugins/agent-relay/hooks/session_delegation_control.py --help
```

## Project structure

Changed only: the five delegation modules, `skills/session-delegation/SKILL.md` if it names any of them, the
delegation tests, `docs/collaboration-interface.md` §10 and §13, and `tasks/cross-host-delegation/`.

## Testing strategy

- `scripts/validate.sh` green (219–220).
- Name scan: no `spec-guard`, `spec_guard`, `Spec Guard`, `.spec-guard` under `plugins/agent-relay/` except the two
  deliberate rejection tests (routing label, result prefix) and the foreign legacy Codex table fixture.
- Mutation: restoring the old result prefix in the controller turns the refusal test red.

## Boundaries

- Always: rename only; keep the schema, lifecycle, authorization rules, and the known defects.
- Ask first: fixing any finding; changing the record schema; reading `~/.spec-guard/session-delegation`.
- Never: launch host sessions here; write host or project permissions; push the repository.

## Success criteria

1. Tests green; old result prefix refused.
2. Name scan clean apart from the listed deliberate lines.
3. Interface §10/§13 updated, including the D12 precondition.

## Open questions

None; D11 and D12 are decided.
