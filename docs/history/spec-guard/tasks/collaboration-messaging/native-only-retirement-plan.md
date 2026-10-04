# Plan: native-only collaboration and XATS retirement

Decision: [`../../docs/decisions/2026-10-04-native-only-collaboration-sunset.md`](../../docs/decisions/2026-10-04-native-only-collaboration-sunset.md)

## Objective

Make the pinned native mailbox the only current collaboration transport, remove the XATS product surface,
and keep historical XATS evidence and private user data outside the runtime path. This is a retirement inside
the existing `collaboration-messaging` module; it does not add a capability-map row or a second map.

## Architecture decisions

- Resolve native directly. An absent legacy selector is not a request for XATS and no fallback remains.
- Preserve the native mailbox schema and exact identity lifecycle; do not migrate or delete user history.
- Move the small ephemeral-config helper needed by Claude delegation into the native delegation path before
  deleting the XATS launcher.
- Remove old runtime and host-adapter code only after all current callers use native contracts.
- Keep immutable historical reports and completed task records, but point current decisions, Specs, skills,
  commands and user documentation at native-only behavior.
- Add a current-surface scan so XATS runtime names and commands cannot silently return outside historical paths.

## Ordered slices

### Slice 1: Decision, inventory, and regression contract

Record the superseding single-user decision and introduce failing native-only contract tests. The tests must
prove that daily collaboration and session delegation neither select nor expose XATS.

### Slice 2: Native-only runtime consumers

Simplify delegation backend resolution, result routing, permission preflight, CLI arguments and skill contracts
to one native backend. Preserve exact recipient matching and no-body result probes.

### Slice 3: Remove the XATS product surface

Delete the XATS runtime, authentication helper, adapters, launcher, selector, archive/activate/rollback tools and
their current tests. Remove their validation entries and update current documentation. Keep only historical
evidence that is clearly labelled as historical.

### Slice 4: Verification and live acceptance

Run focused delegation/collaboration tests, the repository validation suite, phase/artifact guards and smoke
self-test. Install a candidate without altering unrelated global settings, then verify native-only discovery,
two-way exchange, reply, idle wake, exact cleanup and a clear mailbox on one Mac.

## Dependency graph

~~~text
decision + failing contracts
            ↓
native-only consumers
            ↓
delete XATS implementation
            ↓
repository + real-host verification
~~~

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Deleting a helper still used by native delegation | Move the helper first and keep focused create/continue tests green before deletion. |
| Historical evidence fails repository integrity checks | Preserve historical files; scope the retirement scan to current product surfaces. |
| Hidden XATS fallback survives | Negative tests and a source scan reject selector, runtime, adapter and tool names in current entry paths. |
| Native host regression after release | Keep pinned runtime provenance and run one-Mac real-host acceptance before release. |
| User data loss | Never delete either SQLite mailbox; retirement removes code paths, not history. |

## Verification

~~~text
python3 -m unittest discover -s plugins/spec-guard/hooks -p 'test_session_delegation*.py'
python3 -B plugins/spec-guard/hooks/test_native_collab_entry.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_adapters.py
/bin/bash scripts/validate.sh
/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh
/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh
/bin/bash evals/codex-plugin-smoke.sh --selftest
git diff --check
~~~

