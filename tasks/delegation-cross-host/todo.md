# Todo: delegation-cross-host

- [x] Task 1: cross-host only, no host-native (D158, D159) — tests first: `test_session_delegation.py` `test_expired_depth_host_native_or_same_host_fails_closed` (host-native with or without a host permission → `permission-intent`; a host permission on another intent → `host-permission-unexpected`; claude→claude, codex→codex and codex→{claude, codex} → `same-host-unsupported`; claude→codex and codex→claude authorized); the batch test now targets one host; three claim tests moved from codex→codex to claude→codex. `test_session_delegation_recovery.py`: the two same-host tests replaced by "a same-host request is refused before any host starts" (no record left) and "an old same-host record is listed and cancelled but never continued" (record rewritten to codex→codex in SQL; continue → `same-host-unsupported`, no adapter call; cancel works). Red (5 + 2), green after `PERMISSION_INTENTS` drops host-native (`STORED_PERMISSION_INTENTS` keeps old rows readable), `evaluate_authorization` rejects the origin's host among the targets, `continue_named` refuses a same-host claim, and the CLI choices drop host-native. Delegation tests OK on Python 3.10.7 and Apple 3.9.6
- [ ] Task 2: a clear answer when the state cannot be written (D160, controller part)
- [ ] Task 3: skill, README, CHANGELOG (D160 skill part, D161)
- [ ] Checkpoint (report): local validation
- [ ] Task 4: PR and CI
- [ ] Checkpoint (gate): module review
