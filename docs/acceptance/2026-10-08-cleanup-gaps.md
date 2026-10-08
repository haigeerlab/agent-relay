# Acceptance record: cleanup-gaps and the 0.2.1 runtime upgrade (2026-10-08)

Real-host acceptance of `cleanup-gaps` (PR #18, main 813844d; D59–D63, interface 1.1) and of the real runtime upgrade
to 0.2.1 (PR #19, tag v0.2.1 = 5c148d6). The three gaps were found while cleaning up 0.2.0's test leftovers; see
[spec/cleanup-gaps.md](../../spec/cleanup-gaps.md).

## Run

| Field | Value |
|---|---|
| agent-relay commit | 813844d for D59/D60 (runtime bridge still 0.2.0, `runtime bridge OLDER` as expected); 5c148d6 (v0.2.1) for D61 after the runtime upgrade |
| Spec Guard | 0.51.3, then 0.52.0 on both hosts (released during this run; no interface change) |
| Claude Code / Codex | 2.1.291 / codex-cli 0.160.0 |
| Shell environment | D59/D60: `python3` → `/usr/bin/python3` 3.9.6, nvm v12.22.12 first in PATH, no `--node`. D61: v24 first (the bridge runs on the node pinned by the host entry either way) |
| Sessions | throwaway `claude -p --permission-mode dontAsk` sessions allowed only `bridge_register` / `bridge_send`; no host configuration or permission setting changed |

## Results

| Id | Steps taken | Result | Evidence |
|---|---|---|---|
| D60 | `session_delegation_control.py cancel --name r2-cx-review --disambiguator e168ea`, then `269770` (the two round-2 R2-7 records: Codex, `unknown`, thread id set, no turn ever sent) | pass | both `{"state": "cancelled", "prerequisite": "host-thread-absent", "hostOperation": "cancel"}`; before the fix the same calls returned `state: unknown`, `prerequisite: host-request-rejected` |
| D60 boundary | `cancel` on the round-1 Claude-target records `ar-acc-r1fix-c7b`, `ar-acc-r1fix-diag` | pass (unchanged by design) | c7b `state: unknown`, `prerequisite: host-ref-missing`; diag `reason: authorization-expired`. D60 covers only never-turned Codex threads; the user chose to keep both records |
| D59 blocking | `ar-acc-gaps-a` registered; `ar-acc-gaps-b` sends it one message with `expiresInSeconds: 60`; `native_collaboration_retire.py --name ar-acc-gaps-a --confirm-retire` before expiry | pass | `refused`: "still has 1 unacknowledged message(s) (151 queued); read and acknowledge them first" (id and state, no body) |
| D59 expired | message 151 now `expired` (read-only query); same retire | pass | `{"name": "ar-acc-gaps-a", "state": "retired"}`; before the fix an expired message blocked retire and nothing named it |
| Runtime upgrade | all mailbox bridges stopped with the user's agreement (two Claude app bridges, two ChatGPT/Codex bridges), then `native_collaboration_runtime.py upgrade --confirm` from the v0.2.1 checkout | pass | `upgraded`; messages 151, acknowledgements 150, agents 103, wake_jobs 121 kept; backup `~/.agent-relay/backups/20261008T015746Z`; bridge tree 878150e8 `current`. Afterwards preflight: Claude source `current`, Codex cache 0.2.1 `current`, `runtime bridge current`; doctor ok except `codex-approval` (the machine's `guardian_subagent`) |
| D61 refuse | `ar-acc-d61-x` registered, retired; register again (new session); register with `takeover: true` | pass | both refused: "\"ar-acc-d61-x\" was retired at 2026-10-08T01:59:06.877Z by operator. Ask the user: choose a different name, or pass reactivate: true only after the user agrees to bring it back." |
| D61 reactivate | from another session: `reactivate: true` alone; then `takeover: true` + `reactivate: true` | pass | alone: refused by the owner check ("registered by another claude session (no longer running) … pass takeover: true only after the user agrees"), name stays retired (`already-retired`); both: `retiredAt: null`, `reactivated: true`, note "was retired at 2026-10-08T01:59:06.877Z and is reactivated."; retired again afterwards |
| D62 | `interface.json` | pass | `"interface": "1.1"`; Spec Guard's probe range `>=1.0,<2.0` unchanged |
| D63 | — | not run on the real host | covered by the module's fake app-server tests; needs a Codex delegation whose identity was retired before a follow-up |

## Observation

O1. When `reactivate: true` comes from a session that does not own the name, the refusal names only the owner check.
The test session read it as "the name is not retired". Not a defect (both checks are enforced and the name stayed
retired); the message could also say the name is retired.

## Cleanup

| Item | Result |
|---|---|
| Test identities | `ar-acc-gaps-a`, `ar-acc-gaps-b` (cleanup.sh `gaps --confirm`), `ar-acc-d61-x` retired |
| Delegation records | `r2-cx-review` e168ea / 269770 `cancelled`; `ar-acc-r1fix-c7b` / `-diag` kept (user) |
| Host configuration | unchanged |

## Verdict

cleanup-gaps passes on the real host for D59, D60, D61 and D62; D63 rests on its fake app-server tests. agent-relay
0.2.1 is installed and current on both hosts and in the runtime.
