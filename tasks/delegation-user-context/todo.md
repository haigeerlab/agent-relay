# Todo: delegation-user-context

- [x] Task 1: the option is recorded (D162) — tests first: `test_session_delegation.py` (`user-environment` authorized for a Claude target, `user-environment-claude-only` for a Codex target, any other value `host-permission-unexpected`, the request digest differs with it, the stored envelope keeps it after reopening) and `test_session_delegation_recovery.py` (a Codex → Claude Code create with it shows `environment: "user"` in the public payload; without it the payload has no `environment`). Red (no `USER_ENVIRONMENT`; no `environment`), green after `USER_ENVIRONMENT`, the authorization and row checks, `PublicSession.environment`, and the CLI `--user-environment` flag on `create` and `permissions` (replacing the free-text `--host-permission`, which only host-native used). Delegation suites and `test_skill_entrypoints` OK
- [ ] Task 2: the launch (D163)
- [ ] Task 3: the preflight matches the launch (D164)
- [ ] Task 4: skill, README, CHANGELOG (D165)
- [ ] Checkpoint (report): local validation
- [ ] Task 5: PR and CI
- [ ] Checkpoint (gate): module review
