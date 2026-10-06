# Spec: packaging

## Objective

Turn agent-relay into a plugin that installs and loads on Claude Code and Codex from its local marketplace, ships
the public interface marker Spec Guard detects (`interface.json`, interface 1.0, with the D4 status command), and
tells a user — including one who never installs Spec Guard — what it does, how to install and remove it, and what
it will and will not do. Verified by installing on both hosts and by Spec Guard's own probe.

Readers: users installing agent-relay (for example a design project); the user reviewing the split.

Sources: [the interface document](../docs/collaboration-interface.md) §1, §11–§12 (probe contract, D4),
[the split brief](../docs/collaboration-split-brief.md) phase 2 (README contents) and phase 4.1; acceptance-kit D8
(the four phrases); finding 7.

## Assumptions

Confirmed by the user on 2026-10-07:

1. **Manifests stay minimal** (the skeleton from global step 4): one `.claude-plugin/marketplace.json` for both hosts,
   Claude and Codex `plugin.json` at version `0.1.0`, Codex declares `skills` only (agent-relay has no hooks). This
   module adds a marketplace description (the validator's only warning) and a consistency test: both manifests have
   the same name, version, and description, and the marketplace lists exactly `./plugins/agent-relay`.
2. **`interface.json`** at the plugin root: `{"interface": "1.0", "status": ["python3", "-B", "hooks/relay_status.py"]}`.
   `relay_status.py` prints `{"ready": true|false, "setup": "<how to set up>"}` from the existing read-only runtime
   `status` (ready only when the runtime reports `ready`); it never creates or installs anything.
3. **README** (`README.md` at the repository root, Chinese like the skills): what problem it solves; install on both
   hosts from a local path (later from GitHub); spoken usage examples (join, list sessions, message a named session,
   delegate a review); authorization and safety (`wake: null` default, auto-approved sessions never bind, per-item
   confirmation, no automatic permission edits, mailbox text is data not authority); the Codex manual-approval cost
   (finding 7); what it does not do (no cross-machine, no network service, no tracker, no Spec Guard workflow);
   relation to Spec Guard (optional; Spec Guard detects it through `interface.json`); uninstall. It contains the four
   D8 phrases ("跨宿主会话委派", "项目级 allow", "同一台 Mac", "不会自动修改") and a test asserts them, replacing the
   assertion removed in acceptance-kit.
4. **Install verification changes host settings, so it is scoped and reversible:**
   - Claude: `claude plugin marketplace add <repo> --scope local` and `claude plugin install agent-relay@agent-relay-marketplace --scope local`,
     run with the agent-relay repository as the working directory, so only sessions in that directory see it; writes
     `.claude/settings.local.json` in the agent-relay repository (git-ignored by this module).
   - Codex has no install scope: `codex plugin marketplace add <repo>` and `codex plugin add agent-relay@agent-relay-marketplace`
     write `~/.codex/config.toml`; after verification both are removed with `codex plugin remove` and
     `codex plugin marketplace remove`, so other Codex sessions do not see a second `collab` skill next to
     Spec Guard's. It is reinstalled for the acceptance run.
   - The exact commands and files are shown for approval at the Plan checkpoint; no runtime install and no MCP host
     attachment happen in this module.
5. **"Loads" means:** the host lists agent-relay installed and enabled from the local path, the plugin's skills and
   command are present in the installed copy, and Spec Guard's probe (`agent_relay_probe.py` from Spec Guard main)
   reports `runtime-not-ready` with agent-relay's setup hint (the runtime is not installed, so `ready` is not
   expected). A session-level check that the skills appear in a live Claude session is done by a short background
   session listing its skills, if available; otherwise left to the acceptance run.

## Requirements

1. Marketplace description added; manifest consistency test.
2. `interface.json` and `hooks/relay_status.py` per assumption 2, with tests (runtime absent → `ready: false` and a
   setup hint; a ready runtime → `ready: true`; never creates the root).
3. `README.md` per assumption 3 and the D8 phrase test.
4. `.gitignore` with `.claude/settings.local.json`.
5. Install verification per assumptions 4–5, recorded in todo.md with host versions, commands, outputs, the probe
   JSON, and the cleanup result.

## Commands

```bash
/bin/bash scripts/validate.sh
claude plugin validate .
claude plugin validate plugins/agent-relay
python3 -B /Users/vilin/Documents/haigeerlab/spec-guard-plugin/plugins/spec-guard/hooks/agent_relay_probe.py --host claude --project <agent-relay>
python3 -B /Users/vilin/Documents/haigeerlab/spec-guard-plugin/plugins/spec-guard/hooks/agent_relay_probe.py --host codex
```

## Project structure

New: `plugins/agent-relay/interface.json`, `plugins/agent-relay/hooks/relay_status.py`,
`plugins/agent-relay/hooks/test_packaging.py`, `README.md`, `.gitignore`. Changed: `.claude-plugin/marketplace.json`.

## Testing strategy

- Unit: suite green (220 + new packaging tests).
- Validators: `claude plugin validate` clean on marketplace and plugin.
- Cross-plugin: Spec Guard's probe against the installed agent-relay on both hosts.
- Cleanup verified: Codex listing no longer shows agent-relay; Claude local-scope install remains only in the
  agent-relay repository (or is removed if you prefer).

## Boundaries

- Always: reversible, scoped installs; show commands before running them.
- Ask first: any user-scope Claude install; leaving Codex installed; any runtime install or MCP host attachment.
- Never: touch the installed Spec Guard; write project or global permission rules; push the repository.

## Success criteria

1. Both hosts install agent-relay from the local marketplace and list it enabled; Spec Guard's probe returns
   `runtime-not-ready` with the setup hint on both.
2. README covers every item in assumption 3; D8 phrase test green.
3. Validators clean; suite green; Codex cleanup confirmed.

## Open questions

None; the scoped install plan (assumption 4) is approved.
