# Todo: session-routing

- [x] Task 1: `BRIDGE_TRANSPORT` constant, delegation imports, tests (+1 old-value rejection) — 4 routing literals → constant; backend and control import it; moved assertions: test_session_routing (9), delegation backend (1), recovery (1); new `test_the_pre_split_label_is_refused`. 218 tests green. Mutation: setting the constant back to the old value turns test_session_routing red. Remaining literals are the two skill-text assertions, moved with the skills in Task 2
- [x] Task 2: skill text and interface §9 — session-routing skill (4) and session-delegation skill (2) renamed, with their two entry assertions (`test_session_routing_entry.py:111`, `test_skill_entrypoints.py:88`); interface §9 target cell → `agent-relay-bridge` (D1, D10). Name scan: the only `spec-guard-bridge` left under `plugins/agent-relay/` is the deliberate rejection test. 218 tests green
- [x] Checkpoint (gate): module review; never pushed — user accepted 2026-10-07
