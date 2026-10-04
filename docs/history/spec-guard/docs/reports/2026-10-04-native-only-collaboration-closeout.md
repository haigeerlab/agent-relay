# Native-only collaboration closeout — 2026-10-04

## Scope

This report records the source and one-Mac host evidence for retiring the compatibility transport from the
current product surface. It does not rewrite earlier audit or release records. The reviewed source baseline was
`origin/main` at `e8785bacdce1`, followed by the dedicated branch `codex/native-only-xats-retirement`.

The target is one Mac and one current user. Cross-machine support, compatibility with older user installations,
automatic global host-config cleanup, merge, and release are outside this change.

## Result

Native is now the only current collaboration transport in source. Session delegation resolves the pinned native
runtime directly and fails closed when it is unavailable. The old daemon, HTTP/token adapters, Claude launcher,
backend selector, archive/activation/rollback tools, and their live tests were deleted. Historical reports,
decisions, release evidence, proposals, and private mailbox data were retained.

The capability map remains the repository's single map. This work updates the existing
`collaboration-messaging` module and does not add another module or map.

## Verification ledger

| Verification | Status | Evidence |
| --- | --- | --- |
| Native-only RED contract | passed | The initial `test_native_only_collaboration.py` run failed on 10 callable product files and 9 current contract files before implementation. |
| Focused collaboration/delegation regression | passed | 161 tests passed across delegation, routing, daily entry, native runtime/adapters/retirement, host removal, and the retirement scan. |
| Full repository validation | passed | `/bin/bash scripts/validate.sh` exited 0. |
| Phase guard regression | passed | `/bin/bash plugins/spec-guard/hooks/test-phase-guard.sh`: 80 cases. |
| Artifact regression | passed | `/bin/bash plugins/spec-guard/hooks/test-verify-artifacts.sh`: 19 cases. The known modules without `todo.md` remain warnings, not fabricated work. |
| Codex smoke adjudicator self-test | passed | `/bin/bash evals/codex-plugin-smoke.sh --selftest` exited 0. This is a smoke adjudicator check, not host delivery evidence. |
| Native runtime provenance | passed | Source status returned `ready` at pinned revision `8f12c880cfdba73812b6ab7bc0f373fc467e0343`. |
| Claude permission preflight | passed | `permissions --permission safe-review` returned `backend=native`, `ready=true`, `writesPerformed=false`. |
| Codex → Claude creation and Claude → Codex result | passed | A synthetic safe-review Claude session returned `NATIVE_ONLY_ROUND1_OK` on the exact result thread. |
| Same Claude session, second idle round | passed | The same session was continued from `completed/idle`, reconnected the native MCP, preserved its registration, and returned `NATIVE_ONLY_ROUND2_OK`. |
| Direct bridge, Codex → idle Claude → Codex | passed | Message 62 was sent once with wake requested; the target replied `NATIVE_BRIDGE_BIDIRECTIONAL_OK` on the same thread and acknowledged the input. Initial wake was honestly `unknown`; later evidence was `read` with an acknowledgement timestamp. |
| Synthetic cleanup | passed | The Claude session was cancelled; both exact synthetic identities were retired; `bridge_agents(includeRetired=false)` returned count 0. History was retained. |
| Open blocking P1/P2 issues | passed | Read-only `gh issue list` returned three open Proposal issues and no issue labelled P1 or P2. |
| Compatibility rollback rehearsal | not run | Intentionally removed from the retirement gate by `2026-10-04-native-only-collaboration-sunset.md`; no compatibility runtime remains in the current product path. |
| Cross-machine acceptance | not run | Outside the one-Mac product scope. |
| Global Claude/Codex config cleanup | not run | Not authorized in this change. Source removal does not mutate user-global config or delete retained databases. |

No validation failed. No environment-unavailable item remains in the native-only one-Mac acceptance path.

## Residual risks and next actions

1. Merge and release still require normal review; this branch must not merge or publish itself.
2. After a release is installed, host MCP entries should be inspected and refreshed only with explicit user approval.
   This is configuration hygiene, not a compatibility fallback.
3. The first installed-release smoke should repeat the direct bridge exchange and confirm that the installed host
   exposes only the reviewed mailbox tool set.
4. Cross-machine discovery and wake remain unsupported and should not be inferred from this acceptance.

## No longer necessary

- Waiting for a second Mac, a second released version, or an unrelated upstream revision bump before retirement.
- Rehearsing a return to the compatibility transport.
- Maintaining a selector, dual permission catalog, archive/activation path, or fallback tests.
- Creating synthetic Issues or mailbox traffic solely to improve an evidence rating.
