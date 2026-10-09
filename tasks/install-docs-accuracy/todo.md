# Todo: install-docs-accuracy

- [x] Task 1: install states the approvals it writes (D178) — tests first (red): `install-codex` output names the config file, `approval_mode = "approve"` and all ten `[mcp_servers.agent-relay.tools.<tool>]` tables plus the restart hint; `--approve-mailbox-tools` names only the tables it added; collab guard: collaboration-ops says each command prints every table it writes, README says the ten tables are listed. Green after `approvals_written` in both outputs and the two doc sentences. Only `install-codex` writes these tables (checked). Behaviour unchanged; 538 hook tests OK
- [ ] Task 2: Bypass caveat (D179)
- [ ] Task 3: installed paths (D179)
- [ ] Task 4: accurate wording and quoting (D179)
- [ ] Task 5: presence-polish leftovers (D180, bridge)
- [ ] Checkpoint (report): local validation
- [ ] Task 6: PR and CI
- [ ] Checkpoint (gate): module review
