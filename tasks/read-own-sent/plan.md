# Plan: read-own-sent

Based on [`spec/read-own-sent.md`](../../spec/read-own-sent.md) (accepted by the user on 2026-10-16, D212–D214, with the
`direction` field and the refusal wording relayed from the user). Built third in `claude/relay-071-impl`; bridge
commits carry the manifest and `UPSTREAM.md` row (D24). After this module the implementation PR opens; the 0.7.1
release PR (versions, CHANGELOG, READMEs, tag) follows its merge.

## Task List

### Task 1: read one's own sent message by id (D212)
Red first (requirement 1), `bridge/test/long-messages.test.ts` (or a new `read-own-sent.test.ts`): the sender reads its
own direct message and its own broadcast by id, a second part via `bodyOffset`, with `direction: "sent"`; the
recipient's read gives `direction: "received"`; the sender's read leaves the recipient's wake jobs (`readAt`) and
unread state unchanged and records nothing for the sender; expired messages follow today's rule for each role.
Green: `bridge-store.ts` `messagePart` also accepts `from_agent = agent` and returns the direction; `server.ts`
records a read only for a received message.
Files: `src/bridge-store.ts`, `src/server.ts`, one test file.

### Task 2: the refusal says why and whom to ask (D213)
Red first: a third-party id is refused with the agreed wording naming sender and recipient (no hint to read another
inbox); a nonexistent id says there is no such message.
Green: `server.ts` looks the message up only to word the refusal (sender, recipient, existence).
Files: `src/server.ts`, the test file of Task 1.

### Checkpoint (report): bridge green
`npm run check`.

### Task 3: interface 2.2 and docs (D214)
`docs/collaboration-interface.md` (`bridge_inbox` row, version line), `plugins/agent-relay/interface.json` 2.2,
`test_packaging` and other tests that pin the version, `skills/collab` (read one's own sent message by id).
Files: interface doc, `interface.json`, tests, `SKILL.md`.

### Task 4: bridge docs and bookkeeping for 0.7.1
`bridge/CHANGELOG.md` 0.7.1 line, `bridge/INSTRUCTIONS.md` if it describes reading by id, CHANGELOG `[Unreleased]`
(bridge changed, `upgrade --confirm`, plugins first as in 0.7.0, interface 2.2, the three fixes), README and
`README.en.md` only where they describe the changed behaviour.
Files: bridge docs, manifest, CHANGELOG, READMEs.

### Checkpoint (report): local validation
`scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH, bridge `npm run check` included.

### Checkpoint (gate): module review
Implementation PR with all three modules, CI green, the coordinator reviews, the user merges; then the 0.7.1 release PR.
