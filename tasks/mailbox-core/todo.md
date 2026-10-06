# Todo: mailbox-core

- [x] Task 1: code names and state root (D1, D9) with the tests that pin them — `default_root()` = `~/.agent-relay/runtime`, servers `agent-relay`/`agent_relay`, probe client `agent-relay-probe`; moved assertions: adapters (5), host_config (2), host_config_removal fixture name `agent_relay_x` (8) and docstring, runtime comment, and one delegation test (`test_session_delegation_claude.py:97`, deny rule pinned the old server name the delegation code now reads from the adapters). +2 tests (default root, private parent). 217 tests green; `status` on this Mac → `absent`. Left for cross-host-delegation: `test_session_delegation_claude.py:140-155` passes an explicit old server name as a parameter
- [ ] Task 2: skill, command, and reference text
- [ ] Checkpoint (report): names and text translated, tests green
- [ ] Task 3: interface §13 rows and scratch install + probe (network, approval)
- [ ] Checkpoint (gate): module review; never pushed
