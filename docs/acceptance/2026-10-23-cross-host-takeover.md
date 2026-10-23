# Acceptance record: cross-host takeover, Claude ⇄ Codex (2026-10-23)

Checks that one mailbox name can move between a Claude session and a Codex thread with `bridge_register`'s
`takeover`, in both directions, without an interface change (asked for by a plugin whose sessions may switch hosts).
The takeover path (holder-still-running D187, wake rebind D186) does not branch on the host; until now only the
Codex→Claude direction had a unit test, and neither direction had run on the real host. Every host step (opening
or stopping a test session, each takeover, each test message) was approved by the user in the agent-relay
development session first.

## Run

| Field | Value |
|---|---|
| agent-relay | runtime 0.9.0 (installed; not upgraded for this run); unit test on branch commit 98c2289 |
| Claude Code / Codex | 2.1.302 / codex-cli 0.162.1; ChatGPT app 26.1016.61520 |
| Claude test sessions | two desktop sessions in a new empty directory `~/Documents/acc-takeover-claude`, model haiku |
| Codex test thread | one new thread in the test project `relay-codex-test` (project chip checked in a screenshot before typing), thread `01a16832-0140-7831-a33e-c48c78c3b7b9` |
| Test identities | `acc-takeover-c2x`, `acc-takeover-x2c`, `acc-takeover-probe` (the probe is the development session, registered with `wake: null`, used to send the test messages) |

## Unit test

`bridge/test/identity.test.ts`, "a Codex thread takes over a stopped Claude session's name, never a running
one's (D186, D187)" (darwin only, like the other D187 tests, because it uses the fake Claude registry):

- While the Claude holder is in the registry, a Codex caller's `takeover: true` is refused with
  `holder-still-running`, both with `wake: {app: "codex", sessionId}` and with `host` alone; owner, binding and the
  pending ping are unchanged.
- After the holder stops, `takeover: true` with the Codex `wake` moves the owner and the binding to the thread,
  cancels the old session's pending ping, keeps the message in the inbox, says "taken over" with no caveat (the
  registry was readable), lets the thread send as the name and refuses the Claude session.
- With `host` alone the owner moves but the binding stays on the stopped Claude session, as an omitted `wake` does
  for any takeover (D186); moving the binding as well is itself a takeover of the binding and needs `takeover: true`.
- A new bridge process for the same thread (the next turn, H25) registers the name again without `takeover`, with
  no notes, and can send.

No code defect was found; the code is unchanged.

## Results

| Id | Direction | Steps taken | Result | Evidence |
|---|---|---|---|---|
| T1 | Claude→Codex | Claude test session registers `acc-takeover-c2x` with `wake: "auto"` | pass | host and wake `claude` `27afda32-…`; session in the Claude registry (pid 9827) |
| T2 | Claude→Codex | the user agrees; the session is archived (stopped) | pass | pid 9827 gone; no registry entry names the session |
| T3 | Claude→Codex | Codex thread runs `echo $CODEX_THREAD_ID`, then `bridge_register {agent, wake: {app: "codex", sessionId}, takeover: true}` | pass | host and wake `codex` `01a16832-…`; notes: only `"acc-takeover-c2x" was taken over from another session.` (no "cannot confirm": the registry was readable and the holder was gone) |
| T4 | Claude→Codex | probe sends #10531 (`expectsReply`) to `acc-takeover-c2x` | pass (wake) | ping `accepted`, "Codex confirmed a new turn"; the thread's rollout shows a new turn at 09:58:56Z carrying the #10531 preview. It did not reply because the first turn's instruction had said "send nothing" |
| T5 | Claude→Codex | next user turn in the thread: register again **without** `takeover`, then `bridge_send` as `acc-takeover-c2x`, `replyTo` 10531 | pass | register ok, same host and wake, no notes, `unread: 1`; #10536 "Codex 接管后发信正常" reached the probe with `replyTo: 10531` |
| T6 | Codex→Claude | Codex thread registers `acc-takeover-x2c` with its own `wake` | pass | host and wake `codex` `01a16832-…` |
| T7 | Codex→Claude | the user agrees; a second Claude test session registers `acc-takeover-x2c` with `takeover: true, wake: "auto"` while the Codex thread is still open | pass | host and wake `claude` `7939ccbc-…`; notes: `"acc-takeover-x2c" was taken over from another session.` and `The bridge cannot confirm whether the previous Codex session is still running.` |
| T8 | Codex→Claude | probe sends #10538 (`expectsReply`) to `acc-takeover-x2c` | pass | the send returned ping `unknown` ("Ping submitted; awaiting Claude receipt"); the Claude session was woken and replied #10539 "Claude 接管后被唤醒并回信正常", `replyTo: 10538`, 6 s after the send |

## Findings

1. Product behavior, agent-relay (`bridge_register`): a Codex takeover that names its thread with `host` alone
   moves the name but leaves pings bound to the previous (stopped) Claude session, so messages to the name do not
   wake the new thread until it registers again with its `wake` and `takeover: true`. This matches D186 ("omitted
   wake keeps the binding") and the tool text; a host switch should take over with `wake`, not `host`, when the new
   thread is to be woken.
2. Product behavior, informational: taking a name from a Codex thread succeeds even while that thread is open, with
   the "cannot confirm" note (D187: Codex presence cannot be checked here). The previous Codex thread is not told;
   if it later registers the name again without `takeover` it is refused as "registered by another claude session".
3. Test operator note: the first Codex instruction said "send nothing", so the thread was woken (T4) but did not
   answer; sending was then verified in the next user turn (T5).

## Cleanup

Not yet done. The three test identities remain; the first Claude test session is archived, the second is still
open. Retiring the identities, archiving the second Claude session and archiving the Codex test thread wait for the
user's agreement. The test directory `~/Documents/acc-takeover-claude`
holds only a README.
