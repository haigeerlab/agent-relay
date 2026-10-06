# Todo: cross-host-delegation

- [x] Task 1: result route names and state root (D11, D9) + old-prefix refusal test — `RESULT_KEY_PREFIX = "agent-relay-result:"` placed in the core `session_delegation.py` (the controller imports the backend lazily on purpose, so the shared constant lives in the module both already import); idempotency `agent-relay-result-send:`; `<agent-relay-result-route>`; `default_state_root()` → `~/.agent-relay/delegation`. Root creation unchanged from baseline: `DelegationStore` makes the root 0700 with `mkdir(parents=True)`, so a parent it creates gets the default umask mode, as `~/.spec-guard` did; the runtime installer accepts an existing non-private parent. Moved assertions: backend (1), recovery (4); +2 tests (pre-split key refused, default root). 220 tests green; mutation (prefix back to old) → recovery tests red
- [ ] Task 2: control tags and Codex private server/service names
- [ ] Checkpoint (report): delegation names translated, suite green
- [ ] Task 3: interface §10 and §13 (D12 precondition)
- [ ] Checkpoint (gate): module review; never pushed
