# Spec: wake-any-mode

## Objective

The user's principle for round 2 (relayed by the round-2 coordinator, 2026-10-09): the user creates every session and
joins it to the mailbox with one sentence; the communication layer only delivers, wakes and keeps sessions reachable;
what a woken session may do is decided entirely by that session's own permission settings, and when it needs more it
asks the user itself. The communication layer neither lowers nor raises anyone's permissions.

Two things break that today:

1. A Claude Code session in auto mode (the user's default) never binds wake: the collab skill binds only when the
   session "is not auto-approving", so peers on the other host cannot wake it (round-2 test A1; pwa project, wake=null).
2. Every woken Codex turn is forced by the bridge to user approval, `on-request` and a read-only sandbox without
   network (codex-gated-wake D65), with an app-version threshold before the wake (D66a) and a rollout check after it
   that can switch Codex wake off (D66b, `codex-gate.off`).

The user chose (option A, "both sides, no lowering") and confirmed revoking D65. This module makes wake binding work
in every permission mode on both hosts and removes the bridge's per-turn override, keeping the floor that peer content
is untrusted and grants no authority.

Readers: the user; the round-2 coordinator, who runs the real-project acceptance after the whole 0.6.0 batch.

## What exists today (main 09b317a, 2026-10-09)

- `skills/collab/SKILL.md:27`: binds wake only when the user asked to "join and allow wake" **and the session is not
  auto-approving**. `:40-42`: Codex under 帮我批准 may bind; the woken turn is switched to user approval and a read-only
  sandbox; held wakes are explained (old ChatGPT app, or `codex-gate.off`).
- `bridge/src/codex-wake.ts:13-17` `codexTurn`: `approvalsReviewer: "user"`, `approvalPolicy: "on-request"`,
  `sandboxPolicy: {type: "readOnly", networkAccess: false}` on `thread-follower-start-turn` (D65). Peer content goes in
  as the output of an `untrusted_input` function call (kept). `:45-47` holds the wake when the gate is unverified (D66a).
  Before codex-gated-wake the request was `{threadId, input: []}` (commit 2392b40^).
- `bridge/src/codex-gate.ts`: `MIN_CODEX_APP_VERSION = "26.930"`, `gateUnverified`, `gateApplied`, `verifyTurn` (reads
  the woken turn's rollout), `GATE_OFF_FILE = "codex-gate.off"` (D66, D66a, D66b).
- Users of the gate: `wake-dispatcher.ts` (holds Codex jobs, after-turn verification, writes `codex-gate.off`, gate-off
  notice), `notify.ts` (`event: "gate-off"`), `wake-queue.ts` (`turnId` kept for the after-turn check), `server.ts:195`
  (comment). Tests: `bridge/test/codex-gate.test.ts`, `codex-wake.test.ts`, `notify.test.ts`, `support/session.ts`.
- Python: `native_collaboration_doctor.py:198-228` (version threshold and `codex-gate.off` → `codex-approval` warn,
  D68), `native_collaboration_adapters.py:95` (D70 comment), `relay_status.py:4` (interface history). Tests:
  `test_doctor.py`, `test_codex_mailbox_approvals.py`, `test_packaging.py`.
- Docs: README `:80-90` and `:128` describe the gate, the threshold and `codex-gate.off`; collaboration-ops skill
  `:90-95` likewise; CHANGELOG history (left as history).
- Claude wake goes through Claude Code's own cross-session messaging: the receiving session treats the message as a
  teammate's request within its own permissions and cannot be escalated by it; in Bypass permissions Claude Code holds
  such messages and the bridge already explains that (`notices.ts` `CLAUDE_HOLD_EXPLANATION`). The bridge cannot see a
  Claude session's mode (identity-check assumption 6).
- Kept as is: D67 macOS notice when a Codex message cannot be delivered (offline, no binding, busy); D70 the ten
  mailbox tools pre-approved in Codex's config (they only read and write the mailbox).

## Assumptions (accepted by the user 2026-10-09)

1. `thread-follower-start-turn` with `{threadId, input: []}` starts the woken turn under the thread's own current
   approval and sandbox settings, as it did before codex-gated-wake. Checked by the coordinator's real-project
   acceptance (a Codex task under 帮我批准 and one under the default mode, each woken by a Claude peer).
2. Without the override there is nothing left to verify after the turn, so the version threshold (D66a), the rollout
   check and `codex-gate.off` (D66b) and the `gate-off` notice go. The `supportsUntrustedAppInput` refusal stays: it
   protects how peer content enters the turn, not permissions.
3. An existing `codex-gate.off` is ignored after the upgrade and never deleted by agent-relay; doctor says it is no
   longer used and may be deleted.
4. Claude needs no bridge change: binding in any mode is a skill rule; Bypass sessions may bind too, and Claude Code
   may still hold their messages, which the bridge already reports.
5. Interface: this module starts **2.0** (the user chose one breaking release, 0.6.0, for the whole round-2 batch);
   later modules of the batch add to 2.0 without bumping again. The package version is set when 0.6.0 is released;
   this module adds CHANGELOG `[Unreleased]` entries only.

## Decisions

- **D140 D65 is superseded.** The bridge no longer sets `approvalsReviewer`, `approvalPolicy` or `sandboxPolicy` on a
  woken Codex turn; the turn runs under the thread's own settings. Revoking D65 (accepted 2026-10-08) was decided by the
  user in round 2 (option A, relayed) and confirmed by the user's approval of this spec in this session (2026-10-09).
- **D141 the gate machinery goes (D66a, D66b).** `codex-gate.ts`, the version threshold, the after-turn rollout check,
  `codex-gate.off` handling, the `gate-off` notice and the `turnId` kept only for that check are removed. D66 itself
  (auto-approval does not block Codex wake) stands and now needs no gate.
- **D142 any permission mode binds.** collab skill: when the user asks to join and allow wake, bind in every
  permission mode on both hosts (Claude: after checking `thisSession` with `bridge_sessions`, as today). The skill says
  plainly that what a woken session does is governed by its own settings and that it asks the user itself when it
  needs more.
- **D143 the floor stays.** Peer content still enters Codex as an `untrusted_input` tool result and Claude through
  Claude Code's cross-session messaging; mailbox text never grants authority (unchanged wording in collab, the bridge's
  server instructions and `wakeNotice`).
- **D144 doctor and docs say what is true.** doctor's `codex-approval` check reports, as information, that woken Codex
  turns run under the session's own approval settings; when `codex-gate.off` exists it says the file is no longer used
  and may be deleted (`ok`, not `warn`); the version threshold check goes. README, collab and collaboration-ops lose the
  gate, threshold and `codex-gate.off` text and state the risk below.
- **D145 interface 2.0.** `interface.json` and `relay_status.py`'s history note move to 2.0 (breaking batch, 0.6.0).

## Risk (stated in README and the collab skill)

Under Codex 帮我批准 (an automatic reviewer) or Claude auto mode, the woken turn's actions are approved by that
session's automatic reviewer or classifier, not necessarily by a person. That is the user's choice of mode for that
session; agent-relay no longer adds a person in the loop for woken turns.

## Requirements

1. Red first (bridge, `node --test`): `codexTurn` sends exactly `{threadId, input: []}` in `request` (no approval or
   sandbox field) and still carries the `untrusted_input` call with the notice; `wakeCodex` no longer takes a gate
   argument and never returns `held` for version or gate reasons; the dispatcher neither reads nor writes
   `codex-gate.off` and sends no `gate-off` notice; a pre-existing `codex-gate.off` does not hold a Codex wake.
2. Red first (Python): doctor without `codex-gate.off` → `codex-approval` `ok` with the "own settings" detail; with
   the file → `ok` saying it is unused and may be deleted; no version-threshold warning for an old ChatGPT app.
3. `codex-gate.ts` and its test are deleted; remaining tests updated; `scripts/validate.sh` green on Python 3.9, 3.10
   and 3.14 locally and the four CI jobs green.
4. Skill text: collab binds in any mode (D142) and keeps the floor (D143); collaboration-ops drops the gate paragraph.
5. README, CHANGELOG `[Unreleased]`, `interface.json` 2.0 (D145).
6. Acceptance (coordinator, real projects, after the batch): a Claude session in auto mode joins with wake bound and is
   woken by a Codex peer; a Codex task under 帮我批准 is woken by a Claude peer and its turn runs under 帮我批准 (no
   forced approval card for a read); peer content still cannot make either side contact a third party on its own.

## Boundaries

- Always: peer content stays an untrusted tool result; never write `~/.codex/config.toml` or Claude settings.
- Ask first: deleting any user file (including `codex-gate.off`); any change to D70's pre-approved mailbox tools.
- Never: raise a woken session's permissions; bind wake for another session; bypass Claude Code's hold of messages.

## Success criteria

A session in any permission mode on either host can be joined with wake bound and is woken by its peers; a woken
Codex turn runs under that task's own approval settings; nothing in the bridge, doctor or docs refers to a gate that no
longer exists; the untrusted-content floor is unchanged; all tests and CI green.

## Open questions

None. Accepted by the user on 2026-10-09 (assumptions 1–5, D140–D145).
