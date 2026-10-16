# Plan: awaiting-reply-view

Based on [`spec/awaiting-reply-view.md`](../../spec/awaiting-reply-view.md) (accepted by the user on 2026-10-16,
D201–D207; D203's cost cap, D206's native exception and D208 added from the round-2 review of #117). Branch
`claude/awaiting-reply-view-impl` from main after this plan's PR; the round-2 coordinator is told every PR number; the
0.7.0 release PR waits until the implementation PR is merged.

## Task List

### Task 1: schema 6 and the marked send
Red first (requirements 1–2): `bridge/test/schema.test.ts` (5 → 6 and empty → 6 add `expects_reply`, old rows 0; a
build that knows 5 reports `newer` on 6), a new `bridge/test/awaiting-reply.test.ts` (send stores `expectsReply`;
broadcast with it refused; a retry changing it refused). Green: `schema.ts` `SCHEMA_VERSION = 6` and the migration step,
`bridge-store.ts` insert and `MessageView`, `idempotency.ts` `contentDifferences`, `server.ts` `bridge_send` input.
Files: `schema.ts`, `bridge-store.ts`, `idempotency.ts`, `server.ts`, two test files.

### Task 2: the asking view (`bridge_outbox` `awaitingReply`)
Red first (requirements 3–4): open until a linked reply, also after ack; dropped on reply, `failed`, `expired`,
retirement; unmarked never listed; oldest first; `waitingSeconds` from an injected clock; `totalAwaitingReply` beyond
`limit`; presence read once per distinct recipient on the page only, none for retired, none without the flag; a silent
Codex socket costs about 2 s and reads `unknown` with the 2 s detail. Green: `bridge-store.ts` `outbox` filter and
fields, `server.ts` presence lookup with `codexOwner(..., { responseTimeoutMs: 2000 })` mapped to `unknown`.
Files: `bridge-store.ts`, `server.ts`, `presence.ts` (detail constant), `awaiting-reply.test.ts`.

### Task 3: the asked view (`bridge_agents` `owesReplies`)
Red first (requirement 5): only agents with open requests, ids oldest first (at most 20), `oldestAt`; reply or expiry
removes it. Green: `bridge-store.ts` agent summaries (beside `waiting`), `server.ts` output.
Files: `bridge-store.ts`, `server.ts`, `awaiting-reply.test.ts`.

### Checkpoint (report): bridge green
`npm run check` in `plugins/agent-relay/bridge`.

### Task 4: Python hooks (schema 6, D208)
Red first (requirement 6): doctor, `retire` and the delegation backend read a schema-6 fixture; on schema 7 `retire`
and the delegation backend say "update the agent-relay plugin". Green: `MAILBOX_SCHEMA_VERSIONS = (2, 3, 4, 5, 6)`,
wording in `native_collaboration_retire.py` and `session_delegation_backend.py` (the backend surfaces it where it now
returns `None` silently, without changing its result type), `ROLLBACK_CAVEAT` names schema 6.
Files: `native_collaboration_runtime.py`, `native_collaboration_retire.py`, `session_delegation_backend.py`, their tests.

### Task 5: skills, server instructions, interface
`skills/collab` and `skills/session-routing` (D206: mark mailbox requests only, answer marked ones with `replyTo`,
route "谁欠我回复" / "别人在等我回复什么"), the server instructions sentence in `server.ts` (with its test),
`docs/collaboration-interface.md` (D205 fields, 2.x stability for `owesReplies`), `interface.json` 2.1 and the tests
that read it.
Files: two `SKILL.md`, `server.ts`, `docs/collaboration-interface.md`, `interface.json`, entry-point tests.

### Task 6: bridge documents and bookkeeping (D207, D208)
`bridge/INSTRUCTIONS.md` rewritten to the current rules, `bridge/CHANGELOG.md` ("agent-relay 0.5.0" without
"(unreleased)", a 0.7.0 line), delete `bridge/docs/ALTERNATIVES.md` and its link in `bridge/README.md`,
`bridge/UPSTREAM.md` row, `python3 scripts/bridge-manifest.py`; README and `README.en.md` (asking who owes a reply;
upgrade order), CHANGELOG `[Unreleased]` (bridge changed, `upgrade --confirm`, plugins first, transition limit).
Files: bridge docs, manifest, two READMEs, CHANGELOG.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH, bridge `npm run check` included.

### Checkpoint (gate): module review
PR, CI green, the coordinator reviews, the user merges; then the 0.7.0 release PR.
