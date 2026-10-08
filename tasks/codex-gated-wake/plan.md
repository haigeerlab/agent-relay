# Plan: codex-gated-wake

Based on [`spec/codex-gated-wake.md`](../../spec/codex-gated-wake.md) (accepted by the user on 2026-10-08: gate every
mode, visibility B, D65–D69). Branch `claude/codex-gated-wake` from main 2a0d78f. Red → green, one commit per task.

## Task List

### Task 1: Real-App probe (gate) — user agrees first, coordinator told first
On a Codex thread created only for this probe, located by its exact session id (never by time, title or project),
with `config.toml` hashed before and after: wake it with the D65 gate and a message that asks Codex to call
`bridge_inbox`, `bridge_ack` and `bridge_send` and then to `touch` a file. Record from the rollout
(`turn_context`, `thread_settings_applied`) and the App: which of the three MCP calls asked for approval; that the
write asked; whether owner discovery or the turn receipt carries anything that shows the overrides were honoured.
Bring the findings to the user and settle "known to work" (assumption 4) before Task 3.

### Task 2: Every Codex wake turn carries the gate (D65)
`codexTurn`: `turnStart.request` adds `approvalsReviewer: "user"`, `approvalPolicy: "on-request"`,
`sandboxPolicy: {type: "readOnly", networkAccess: false}`; `threadId`/`conversationId` stay the bound session id.
Tests on the payload.

### Task 3: Auto-approval no longer blocks Codex wake; fail closed (D66)
Remove the refusal in `bridge_register` and the hold in `wake-dispatcher`. Gate checks (spec Amendment 2): D66a
ChatGPT app version ≥ 26.930 before the wake, else `held`; D66b after an accepted turn, the exact thread's rollout
`turn_context` for that `turn.id` must show user / on-request / read-only, else write `<mailbox dir>/codex-gate.off`,
notify once, and hold later Codex jobs. Tests with injected version and rollout readers: auto-approved config → bind
and wake gated; old or unknown version → held; matching rollout → nothing; mismatch or missing → gate off + one
notice + next job held; `codex-gate.off` present → held; non-Codex unchanged.

### Task 3b: Pre-approve the mailbox tools for Codex (D70)
`install-codex` writes `[mcp_servers.agent_relay.tools.<tool>]` / `approval_mode = "approve"` for the ten
`MAILBOX_TOOLS`, skipping tools that already have one; new `install-codex --approve-mailbox-tools` adds only the
missing subtables to an existing matching entry (backup first, refuse on any other difference); uninstall unchanged.
Tests: fresh install, existing user-written subtable kept once, option on a matching entry, refusal on a mismatch,
uninstall removes all, nothing written to `~/.codex/rules`.

### Task 4: Notify the user when a Codex message cannot be delivered (D67 B)
On a Codex wake that ends `pending` offline, `held`, or a direct message to a Codex recipient without a wake binding
(at once), or `pending` busy still undelivered after 10 minutes: one macOS notification per message (`osascript -e 'display notification …'`, sender and message id, no
body), through an injectable notifier; an environment switch turns it off; never on non-macOS. The sender's
`bridge_send` result (and wake status) says the user was notified. Tests with a fake notifier: once per message,
busy silent before 10 minutes, notified once at 10 minutes, and never if delivered within 10 minutes; text without body, switch off, Claude recipients unaffected.

### Task 5: doctor `codex-approval` (D68)
Accurate text (selector per turn, not in `config.toml`; peer turns gated), `ok` when gated; no instruction to edit
`config.toml`. Tests.

### Task 6: Interface 1.2 and docs (D69)
`interface.json` 1.2 and its test; interface doc rows; skills `collab` / `collaboration-ops` / reference text about
帮我批准; README; `bridge/UPSTREAM.md` + manifest; CHANGELOG `[Unreleased]` with `upgrade --confirm`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 7: Live (temporary `AGENT_RELAY_HOME`/HOME, coordinator told first)
Runtime from this checkout; a fake Codex IPC socket under the temporary HOME records the
`thread-follower-start-turn` payload (gate fields, exact thread); auto-approved temporary `config.toml` → bind and
wake gated; an offline Codex recipient → one notification through a fake notifier, sender told. Real-App end to end
is the coordinator's acceptance after release.

### Checkpoint (gate): module review
