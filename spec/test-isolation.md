# Spec: test-isolation

## Objective

One environment variable relocates agent-relay's whole state root, and the test run can never read or write the
real one. This is the first hardening module (brief item 7, interface §13 row "State root override", gap j);
`bridge-vendoring`, `delivery-state-machine` and the later modules write tests that start bridges and mailboxes, and
those must run against a throwaway root.

Readers: the user reviewing hardening; agents building the later hardening modules; the round 2 operator.

Sources: [interface](../docs/collaboration-interface.md) §13 and gap j; [brief](../docs/collaboration-split-brief.md)
phase 3 item 7; the measurements below.

## What exists today (measured, 2026-10-07, main 60f4ddd)

- The state root `~/.agent-relay` is derived from `Path.home()` in three places:
  `native_collaboration_runtime.default_root()` → `~/.agent-relay/runtime` (used as the default `--root` of the
  runtime, adapters and retire CLIs, `relay_status.py`, `scripts/acceptance/preflight.sh` and `cleanup.sh`);
  `session_delegation_control.default_state_root()` → `~/.agent-relay/delegation`;
  `state_migration` → `--home` (default `Path.home()`) + `.agent-relay` for the target runtime, delegation db and
  `backups/`.
- The bridge itself honours `BRIDGE_DB_PATH` and `XDG_DATA_HOME`; the adapters already derive both from the root,
  so a moved root moves the mailbox with it. `install-claude` / `install-codex` write these two as absolute paths
  into the host's MCP entry at install time (`native_collaboration_adapters._paths`).
- Every CLI already takes an explicit root flag (`--root`, `--state-root`, `--native-root`, `--home`), but nothing
  moves all of them at once.
- **Tests are already isolated in practice:** `scripts/validate.sh` with `HOME` set to an empty temporary directory
  passes all 274 tests and leaves that directory empty. Tests that need a home patch `Path.home` or pass temporary
  roots. Nothing stops a future test from reaching the real root, though, and `validate.sh` runs with the user's
  `HOME`.

## Assumptions

Confirmed by the user on 2026-10-07 (name `AGENT_RELAY_HOME`, relative path refused); the round 1 owner's
acceptance points (entry-point sweep, host entries, live check scope) are folded into the requirements.

1. **The variable is `AGENT_RELAY_HOME`**, naming the state root itself (default `~/.agent-relay`): runtime at
   `$AGENT_RELAY_HOME/runtime`, delegation at `$AGENT_RELAY_HOME/delegation`, migration backups at
   `$AGENT_RELAY_HOME/backups`.
2. **Precedence:** an explicit flag (`--root`, `--state-root`, `--native-root`) wins over `AGENT_RELAY_HOME`, which
   wins over `~/.agent-relay`. An empty value counts as unset; a relative path is refused with a clear error (exit 2)
   rather than resolved against whatever the current directory is.
3. **Host configuration is out of scope.** `~/.claude.json`, `~/.claude/settings.json` and `~/.codex/config.toml`
   belong to the hosts; tests already redirect them with `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and patched paths. When
   the runtime is attached to a host under a moved root, the entry gets that root's resolved absolute paths. The
   variable is read when a command runs: it does not move an already attached host entry, which keeps pointing at
   the root it was installed with until it is attached again.
4. **Migration:** the source (`~/.spec-guard/…`) stays under `--home`; the target follows `AGENT_RELAY_HOME`.
5. **No behaviour change with the variable unset:** every default path stays byte-identical; installed users notice
   nothing.
6. **Verification is unit tests plus one live check** that a moved root works end to end on this Mac (install the
   runtime under a temporary `AGENT_RELAY_HOME`, read its status, remove it). No host session is started.

## Decisions

D21 and D22 accepted with the spec on 2026-10-07.

- **D21 one helper.** `native_collaboration_runtime.state_home()` returns the root from the variable or the default
  (and validates it); `default_root()`, `default_state_root()` and the migration target are all derived from it.
  No second copy of the rule.
- **D22 the test run is sealed.** `scripts/validate.sh` runs every test file with `HOME`, `AGENT_RELAY_HOME`,
  `CLAUDE_CONFIG_DIR` and `CODEX_HOME` set to a fresh temporary directory, removed afterwards, so no test can reach
  the user's state or host configuration even by accident. A test asserts that inside the run the default root is
  not the user's real `~/.agent-relay`.

## Requirements

1. With `AGENT_RELAY_HOME=/x`, every entry point uses `/x/...` for the whole state root (runtime, mailbox,
   delegation, backups): runtime, adapters and retire CLIs, `relay_status.py`, the delegation controller, the
   migration target, `scripts/acceptance/preflight.sh` and `cleanup.sh`. With it unset, paths are unchanged.
   An **entry-point sweep test** runs each of them (or its default-path function) with the variable set to a
   temporary root and asserts every path it reports or would use is under that root, and a source scan asserts
   no module outside the helper builds `.agent-relay` from the home directory.
2. `install-claude` and `install-codex` write `BRIDGE_DB_PATH` and `XDG_DATA_HOME` as the resolved absolute paths
   under `$AGENT_RELAY_HOME` (tested against fixture host configs).
3. Explicit flags still win; an empty variable is ignored; a relative one exits 2 with a message naming the variable.
4. `validate.sh` seals the run as in D22 and still reports `N files, M tests` / `validate: pass`.
5. README, `collaboration-ops` skill and interface §13 document the variable, including that it does not move an
   already attached host entry (re-attach after moving the root); interface gap j is marked done.

## Commands

```bash
/bin/bash scripts/validate.sh
AGENT_RELAY_HOME=<tmp> python3 -B plugins/agent-relay/hooks/native_collaboration_runtime.py status
```

## Project structure

Changed only: `native_collaboration_runtime.py`, `session_delegation_control.py`, `state_migration.py` (and the
CLIs that take their defaults from these), their tests, `scripts/validate.sh`, `scripts/acceptance/*.sh` if they
print or derive the root, `README.md`, `skills/collaboration-ops/SKILL.md`, `docs/collaboration-interface.md`, and
`tasks/test-isolation/`.

## Testing strategy

- Unit tests for `state_home()`: unset, set, empty, relative; each derived default follows it; flags win.
- A sealed-run test (D22): inside `validate.sh` the default root is under the temporary directory.
- Mutation: ignoring the variable in `state_home()` turns the derivation tests red.
- Live (round 1 owner told first): runtime `install` and `status` under a temporary `AGENT_RELAY_HOME`, then
  removed; the real `~/.agent-relay` file list and the host configuration files are unchanged before and after. No
  host attach, no host session.

## Boundaries

- Always: keep default paths identical; derive every root from the one helper.
- Ask first: any change to host configuration handling; moving the real `~/.agent-relay`.
- Never: write into the user's `~/.agent-relay` from tests; push without approval.

## Success criteria

1. All tests green in the sealed run; the derivation and validation tests fail when the helper ignores the variable.
2. The live moved-root check passes and leaves the real root untouched.
3. Docs and interface updated.

## Open questions

None.
