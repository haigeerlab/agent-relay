# Plan: install-docs-accuracy

Based on [`spec/install-docs-accuracy.md`](../../spec/install-docs-accuracy.md) (accepted by the user on 2026-10-09:
assumptions 1–6, D178–D179; assumption 7 / D180 added 2026-10-10 from the review of #66, accepted with this plan).
Branch `claude/install-docs-accuracy` from main after the `presence-polish` closeout. Last module of 0.6.1. The
round-2 coordinator is told the PR number; no release before it has reviewed all three module PRs and the user agrees.

Read while planning: `install-codex` prints one line and `--approve-mailbox-tools` its own result
(`native_collaboration_adapters.py:282-290`); the ten tables come from `:98`. README runs scripts by repository path
at lines 78, 160–161 and by bare name elsewhere (86, 180, 193, 196, 205, 218); three skills already carry the
`agent-relay-root` block (guarded by `test_plugin_root.py`), collab does not. session-routing quotes user text in
single quotes twice (`'<json>'` and `resolve --name '<名字>'`). The two "never edits" texts are
`native_collaboration_adapters.py:208` and `state_migration.py:498`. The Housekeeper ticks every 5 s
(`housekeeping.ts:52`).

## Task List

### Task 1: install states the approvals it writes (D178)
Red first (`test_native_collaboration_adapters.py`): `install-codex` output names all ten tools and shows the table
form `[mcp_servers.agent_relay.tools.<tool>] approval_mode = "approve"`; `--approve-mailbox-tools` names the tables it
added (or says none were missing). README install section and collaboration-ops upgrade steps say the same.
Behaviour unchanged (existing tests stay green).

### Task 2: Bypass caveat (D179)
Red first (skill guard): collab says binding works in any mode but a Bypass-permissions Claude session holds incoming
pings for approval (the desktop app lets them expire) unless the user sets `crossSessionInbound`, linking
`BACKGROUND-WAKE.md`; README says the same next to wake binding. No setting changed.

### Task 3: installed paths (D179)
Red first (guard in `test_skill_entrypoints.py` or a README test): README has no `plugins/agent-relay/hooks/` command
outside the developer section; one subsection "找到插件目录" defines `<插件目录>` (the same resolution as the
`agent-relay-root` block, plus what `claude plugin list` / `codex plugin add` show, checked on this Mac); every README
command uses `<插件目录>/hooks/…`; collab gains the `agent-relay-root` block (`test_plugin_root.py` covers it).

### Task 4: accurate wording and quoting (D179)
Red first: the two "never edits" texts say what is true (no allow rules are added to the user's settings; uninstall
removes only the deny rules 0.4.0 wrote); session-routing states the single-quote rule (`shlex.quote`: `'` → `'\''`)
with one example, for both `select` and `resolve --name`, uses no heredoc (existing guard), and a test runs a command
built by the rule under `bash` and `zsh` with `'`, `$(…)`, backticks and `$HOME` in a name and body: the selector (and
`resolve`) receive the text verbatim, nothing expanded or executed.

### Task 5: presence-polish leftovers (D180, bridge)
Red first: a Housekeeper tick removes `notified/episode-<session>` for a session with nothing in `claudeWaiting` and
keeps the one still waiting; the `bodyOffset` error names `bodyLength ?? body.length`. `UPSTREAM.md` and manifest in
the same commit.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10 and 3.14; CHANGELOG: `--host-permission` removal added to the 2.0
breaking list, `[Unreleased]` entry. (The `[0.6.1]` section with upgrade and rollback steps — delegation store
schema 2 → 3, runtime upgrade, restoring `delegation.schema2.sqlite` to go back — is written in the release PR.)

### Task 6: PR and CI
Push, open the PR, tell the coordinator the PR number; the four CI jobs green.

### Checkpoint (gate): module review
The coordinator reviews the PR; the user merges; then the 0.6.1 release (only after the coordinator has reviewed all
three module PRs and the user agrees).
