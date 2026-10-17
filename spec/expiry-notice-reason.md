# Spec: expiry-notice-reason

## Objective

Only module of 0.7.2 (bridge). A usage observation on 2026-10-17 found that a Claude recipient whose session was simply
stopped got a delivery-failure notice blaming Bypass permissions and Claude Code's `crossSessionInbound` setting. The
notice sends the user to loosen a security setting, which cannot help, and never says the one useful thing: open that
session. The user decided on 2026-10-17 to fix this first, as its own small module ("先修第 6 条"; "确认插入
expiry-notice-reason 模块，假设没问题").

Readers: the user; the round-2 coordinator and the usage observer (re-check after release).

## What exists today (main 9dec39c, v0.7.1)

`bridge/src/notices.ts` decides that a failed Claude ping was *held by Claude Code* with

```ts
job.target.app === "claude" && (job.state === "held" || /\b(expired|held)\b/i.test(job.detail))
```

The regex is meant for Claude's own receipt `"Claude expired this peer message"` (`claude-wake.ts`, state `refused`).
But when the one-hour retry window lapses for an offline recipient, `wake-queue.ts` writes the detail
`"Wake retry window expired; message remains unread"`, which also contains the word *expired*. So every Claude offline
expiry gets `CLAUDE_HOLD_EXPLANATION`. Observed: message #4017, `pendingReason: "offline"` on all 63 retries, recipient
presence `stopped`; the expiry notice #4137 explained a permission hold.

The same misjudgement sits in two more places that attach the same explanation:

1. `server.ts`, `bridge_wake_status` list mode: `explanation` is added when any listed Claude job matches
   `/expired|held/i` — so one offline expiry in the last 100 jobs adds it.
2. `addressing.ts`, the send-time warning "The last 3 background pings … were not delivered": the explanation is
   appended whenever the recipient is a Claude session, whatever the three failures were.

Found in the round-2 review of #126 (coordinator, 2026-10-17), accepted by the user:

3. `bridge/INSTRUCTIONS.md:16`, the guidance agents read, says pings to a Claude session that were "held or expired"
   mean Bypass permissions — after the code fix an agent would still send the user to change permissions.
4. `REARMED_DETAIL` (`wake-queue.ts`) also contains *expired* ("the earlier ping expired while it was away"), so a
   re-armed Claude job that is still pending or accepted already adds the hold `explanation` in `bridge_wake_status`.

## Assumptions (accepted by the user 2026-10-17)

1. **Scope is only how the explanation is chosen**: `notices.ts` (`isClaudeHold`, `explainFailure`), the
   `bridge_wake_status` list-mode explanation, and — found while writing this spec, same defect — the send-time warning
   in `addressing.ts`. Retries, expiry, notice throttling and every other behaviour stay as they are.
2. **A Claude hold is recognised only from Claude itself**: the job state is `held`, or the job was finished by Claude's
   own receipt (`refused` with detail `"Claude expired this peer message"`). An offline or unreachable expiry is never a
   hold.
3. **New text for a Claude offline expiry** (state `expired`, `pendingReason: "offline"`): the session was not running
   for the whole one-hour retry window (the Claude app may stop idle sessions); the message is still in the inbox and is
   delivered once the user opens that session. No mention of Bypass permissions or `crossSessionInbound`. Codex
   recipients, `busy` and `unreachable` keep their current text.
4. **Notices stay in English**, like every bridge notice; translating them is out of scope.
5. **Version**: text and selection only; no tool parameter or result field changes. Interface stays 2.2, mailbox
   schema 6, delegation store schema unchanged. Released as 0.7.2, a bridge change, so it needs `upgrade --confirm`;
   the release itself waits for the user.
6. **Verification**: a failing test first reproduces "offline expiry gets the hold explanation", then the fix; a
   real-host re-check is arranged separately.

7. **Review additions (accepted by the user 2026-10-17)**: `bridge/INSTRUCTIONS.md` is corrected the same way (hold =
   `held` or Claude's own expiry receipt; an offline expiry = not running, ask the user to open it); a re-armed job is
   covered by a test; and when the latest of the three failures in the send-time warning is a Claude offline expiry,
   the warning carries the same "not running; ask the user to open it" sentence as the notice.

## Decisions

- **D215 only Claude's own word makes a hold.** One predicate, shared by the delivery-failure notice, the
  `bridge_wake_status` list explanation and the send-time warning, says a Claude ping was held: state `held`, or state
  `refused` with Claude's expiry receipt. A Claude ping that expired because the session was not running is explained
  as "not running; ask the user to open it", in the notice and in the send-time warning alike. Assumptions 1–4, 7.

## Requirements

1. Red first, `bridge/test/delivery.test.ts`:
   - a Claude job that expires with `pendingReason: "offline"` produces a notice that says the session was not running
     and asks the user to open it, and does **not** contain `crossSessionInbound` or `Bypass`;
   - a Claude job that expires with `pendingReason: "unreachable"` gets the existing "unreachable" text, no hold text;
   - the existing case (`refused`, `"Claude expired this peer message"`) still gets `CLAUDE_HOLD_EXPLANATION`;
   - a `held` Claude job still gets it; a Codex job never does.
2. Red first, `bridge_wake_status` list mode (`bridge/test/mcp-integration.test.ts`): a list holding only offline
   expiries has no `explanation`; a list holding only a re-armed Claude job (detail `REARMED_DETAIL`) has none; a list
   holding one real Claude hold has it.
3. Red first, `bridge/test/lifecycle.test.ts`: three Claude offline expiries give the "last 3 background pings" warning
   without the hold explanation and with the "not running; ask the user to open it" sentence; three Claude expiry
   receipts (the existing case) still include the hold explanation.
4. `notices.ts` exports the single predicate (D215); `server.ts` and `addressing.ts` use it instead of their own checks.
   `explainFailure` gains the Claude-offline branch (assumption 3); the notice and the warning share that sentence.
5. Bridge bookkeeping in the same commit (D24): `UPSTREAM.md`, `python3 -B scripts/bridge-manifest.py`; CHANGELOG
   `[Unreleased]`; `bridge/INSTRUCTIONS.md` (the "held or expired" sentence, assumption 7); `docs/BACKGROUND-WAKE.md`
   if it describes when the hold explanation appears.
6. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Always: tests first; only how the explanation is chosen and the one new text.
- Ask first: any test notice sent on this Mac's real mailbox; translating notices; any change to `CLAUDE_HOLD_EXPLANATION`
  itself.
- Never: change retry windows, expiry, throttling, pending reasons or any schema; let the bridge touch
  `crossSessionInbound` or any Claude Code setting.

## Acceptance (after 0.7.2)

- A message to a stopped Claude session, left until its ping expires, yields a notice whose "Why" says the session was
  not running and asks the user to open it; `bridge_wake_status` for that recipient carries no hold `explanation`.
- Code review: one shared predicate; no `/expired|held/` regex left on wake details.

## Open questions

- None for this module. Items 1–3 of the same observation (open-request closing, `bridge_agents` size, read rules) and
  presence idle/busy are separate modules.
