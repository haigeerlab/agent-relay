# Spec: codex-gated-wake

## Objective

Most users run Codex with 帮我批准 (`approvals_reviewer = "guardian_subagent"`). Today the bridge then refuses Codex
wake bindings and holds every ping (identity-check D38), so nobody sees that a peer handed Codex work and the
collaboration stops silently. Requirements from the user (via the coordinator, 2026-10-08):

1. Must: in every approval mode, an arriving message is visible to the user ("session X gave Codex work").
2. Should: under auto-approval, Codex is still woken, but the woken turn can act only with the user's approval; the
   user's own conversation keeps 帮我批准.
3. Floor, unchanged: peer content never triggers execution without a person approving.

Readers: the user; the coordinator ("第二轮联调"), who probed the Codex App.

## What exists today (measured, main 2a0d78f, 2026-10-08)

- `bridge/src/server.ts:181`: `bridge_register` with a Codex wake target throws `codexAutoApprovalText` when
  `codexApproval()` says auto-approved.
- `bridge/src/wake-dispatcher.ts:84`: a due Codex job under auto-approval finishes `held` with the same text; the
  message stays `queued`.
- `bridge/src/codex-wake.ts` `codexTurn`: `thread-follower-start-turn` to the bound `job.target.sessionId` with
  `turnStart.request = {threadId, input: []}` — no approval or sandbox override; the peer text is an
  `untrusted_input` tool result. `wakeNotice` already names the sender, a preview, the recipient and the mailbox.
- `hooks/native_collaboration_doctor.py:179`: `codex-approval` warns and says to switch the App selector to 请求批准.
  The selector is applied per turn and is not written to `config.toml` (R2-2), so that advice is inaccurate.

## Coordinator's probe (Codex App 26.930, CLI 0.160, disposable test thread, `config.toml` hash unchanged)

- `turnStart.request` reaches `turn/start` unchanged; `approvalsReviewer`, `approvalPolicy`, `sandboxPolicy` apply to
  that turn (`turn_context`, `thread_settings_applied`).
- `approvalsReviewer: "user"` + `approvalPolicy: "untrusted"` is not enough: sandbox stays workspace-write and a
  `touch` inside the project ran without a prompt.
- `approvalsReviewer: "user"` + `approvalPolicy: "on-request"` + `sandboxPolicy: {type: "readOnly",
  networkAccess: false}`: a write asks for escalation, the App shows an approval card (deny / allow once) and marks
  the thread "waiting for approval". Deny → nothing ran; allow once → it ran. Both observed.
- The user's next own message restores on-request + auto_review; the override does not persist.
- **Not verified:** whether `bridge_inbox` / `bridge_ack` / `bridge_send` (MCP tools) ask for approval under that
  gate. The user's expectation: reading and replying need no approval, acting does.
- The first probe picked a thread by mtime and woke a real thread of another project (Codex declined; nothing
  changed). Every thread choice must use the bound session id.

## Assumptions

Confirmed by the user on 2026-10-08: gate every mode (assumption 1), visibility B (assumption 3), the rest as written.

1. **Every Codex wake turn is gated, in every approval mode:** `turnStart.request` carries
   `approvalsReviewer: "user"`, `approvalPolicy: "on-request"`, `sandboxPolicy: {type: "readOnly",
   networkAccess: false}`. One rule for all modes; a peer turn can read but cannot write or reach the network
   without the user's approval card. (Alternative: gate only under auto-approval and leave other modes as today.)
2. With the gate, auto-approval no longer refuses a Codex wake binding or holds its pings (D38's refusal and hold
   are removed); `config.toml` is still read, now only for doctor's information.
3. **Visibility (requirement 1), for the user to choose:**
   - **A (minimum):** the gated woken turn is the signal: it appears in the user's Codex thread with the sender, a
     preview and "Peer content is not user approval"; anything it wants to do shows an approval card and the
     "waiting for approval" mark. When it cannot be delivered (Codex not running, busy, no wake binding, or the gate
     unverified and the job held) the message stays `queued` and only the sender's `bridge_send` warnings say so.
   - **B (coordinator's suggestion):** A, plus a macOS notification from the bridge in exactly those undeliverable
     cases (`osascript` `display notification`, naming the sending session and the message id, never the body), at
     most once per message; the sender's result says the user was notified. Cost: a new outward side effect of the
     bridge, a rate limit, and an opt-out switch.
4. **Fail closed:** the gate is only sent where it is known to work. The bridge requires the Codex owner to advertise
   support the probe relied on; if the probe in Task 1 finds no reliable signal, the bridge keeps D38's hold for
   auto-approved sessions on unverified Codex versions rather than wake ungated.
5. Waking targets only the bound `sessionId` (already so in `codexTurn`); no code path chooses a thread by time,
   title or project. Probes in this module follow the same rule, on a disposable thread, with the user's consent.
6. doctor's `codex-approval`: `ok` when wake turns are gated, with an accurate note (the App selector applies per
   turn and is not stored in `config.toml`; peer turns run read-only and ask the user before acting).
7. Interface 1.1 → 1.2: an auto-approved Codex session can now bind wake (documented behaviour changes,
   backward-compatible inside 1.x).
8. Vendored-bridge change (UPSTREAM.md, manifest); users get it through `upgrade --confirm`. Ships with
   `register-retired-hint` in the next release.

## Decisions

- **D65 every Codex wake turn carries the approval gate, in every approval mode.** As assumption 1. Accepted on 2026-10-08.
- **D66 auto-approval no longer blocks Codex wake.** As assumptions 2 and 4 (fail closed where the gate is unverified). Accepted on 2026-10-08.
- **D67 visibility B.** The gated turn, plus a macOS notification when a Codex message cannot be delivered (not running, busy, no wake binding, held), naming the sending session and message id, never the body, at most once per message, switchable off; the sender's result says the user was notified. Accepted on 2026-10-08.
- **D68 doctor states the selector accurately.** As assumption 6. Accepted on 2026-10-08.
- **D69 interface 1.2.** As assumption 7. Accepted on 2026-10-08.

## Requirements

1. Task 1 probe (real Codex App, disposable test thread created for it, exact session id, coordinator told and the
   user agrees first; `config.toml` hash before/after): under the gate, do `bridge_inbox`, `bridge_ack`,
   `bridge_send` ask for approval? Is there a field in owner discovery or the turn receipt that shows the overrides
   were applied? Record both; the answers settle assumption 4 and the user-facing text.
2. Bridge tests: `codexTurn` carries the three overrides and the bound thread id only; an auto-approved config no
   longer refuses `bridge_register` with a Codex wake target nor holds the job (wakes with the gate); the fail-closed
   path of assumption 4 holds; non-Codex wakes unchanged.
3. doctor and its tests: new `codex-approval` text; no instruction to edit `config.toml`.
4. Docs: interface doc rows (`bridge_register` wake, delivery), skills `collab` / `collaboration-ops` text about
   帮我批准, README, CHANGELOG `[Unreleased]` (with `upgrade --confirm`), `interface.json` 1.2, UPSTREAM.md + manifest.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; bridge `npm run check` green.
6. Live: in a temporary root, a fake Codex IPC socket records the `thread-follower-start-turn` payload (gate fields,
   exact thread). Real-App end to end (approval card, deny / allow once) is the coordinator's acceptance after the
   release, on a disposable thread.

## Boundaries

- Always: target the bound session id; never wake an ungated turn under auto-approval.
- Ask first: any real Codex App / real `~/.agent-relay` action, including the Task 1 probe.
- Never: edit `~/.codex/config.toml`; push without approval.

## Success criteria

Tests and live check pass; after release the coordinator sees, on a disposable thread under 帮我批准, the woken turn
with sender and preview, an approval card for any write, deny → nothing, allow once → done, and the user's own next
turn back on 帮我批准.

## Open questions

- Assumption 4: what counts as "known to work" is settled by the Task 1 probe and brought back to the user.
