# Native wake failure and fork smoke — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **isolated absent, held and fork cases exercised; Task 1 remains open**. This run used
upstream revision `8f12c880cfdba73812b6ab7bc0f373fc467e0343` and a new private mailbox under
`/private/tmp`. No XATS production mailbox, project code, Chrome setting or persistent host MCP
entry was changed. A temporary Claude CLI session loaded the communication tools through
`--mcp-config`; noncommunication tools were denied. The sender was an isolated MCP probe, not a
second live Codex Desktop conversation, so this does not repeat the earlier host-to-host wake
proof.

## Absent session and recovery

- Claude self-registered `trial-claude-absent` with `wake: "auto"`. After that background session
  was stopped, sending test message **1** returned a warning that its Claude conversation was not
  running. The message stayed unacknowledged, and the wake job was `pending` with `offline` reason.
- An attempt to resume while passing additional CLI options created a **copy** with a new session
  ID. That copy read and acknowledged message 1, so it proved mailbox persistence but **not**
  original-session recovery. It was stopped. This is also an access-boundary observation: the
  bridge's mailbox tools are not scoped to the caller's registered session.
- A second offline test message, **4**, was sent to the same stopped original. Running
  `claude --bg --resume <original-session-id>` **without overriding its saved options** woke the
  original session, which read and acknowledged 4. Its wake record separately carried an
  `acknowledgedAt` timestamp. As in the earlier smoke, the `read` detail still incorrectly said
  work was not acknowledged; consumers must not use that stale detail as the handling truth.

## Explicit hold

- A fresh Claude session registered `trial-claude-held` with temporary
  `--settings '{"crossSessionInbound":"hold"}'` and ordinary permission mode. Test message **2**
  entered the mailbox. A probe launched under the sandbox initially reported a false offline
  condition because it could not see the live Claude socket; the same pinned probe outside that
  sandbox retried and recorded `held`. The recipient did not fetch or acknowledge message 2.
- The sender received automated delivery notice **3**, which was read and acknowledged by the
  test harness. The original message remained unread, as intended. The upstream explanation for
  this explicit-hold case misleadingly claimed that the recipient ran in Bypass permissions and
  suggested a global `accept` setting. The recipient actually ran in default permission mode with
  an explicit per-session hold. This explanatory text is **not accurate enough for daily use**;
  a Spec Guard adapter must report the observed `held` state without attributing an unproven
  cause or recommending a global permission relaxation.
- A Bypass-mode hold was **not** tested: Claude required an interactive disclaimer before a
  background Bypass session, and this trial did not accept or work around that disclaimer.

## Fork binding

- `--fork-session` gave the fork a new Claude session ID. The first fork did not inherit the
  temporary MCP launch configuration, so it could not run the test and was stopped without using
  the separate production collaboration server it saw. A second fork passed the same temporary
  MCP configuration explicitly.
- The second fork's `wake: "auto"` attempt to register the live original's name
  `trial-claude-held` was rejected as bound to a different live Claude session. It then registered
  `trial-claude-fork` with its own ID; the original binding and held message remained unchanged.
  This supports distinct Claude fork identity, but the normal one-step `collab` entry still needs
  its own acceptance test.

## Cleanup and remaining gates

- The original, held and forked trial Claude background sessions were stopped. The isolated
  sender notice was acknowledged. Message 2 was intentionally left unread at the moment of
  trial cleanup because `hold` correctly kept it away from the recipient model; it is test-only
  data, not user work. The temporary mailbox and checkout were removed after this record.
- No persistent Claude or Codex MCP config was added in this run. Existing XATS remains the
  default. Task 1 remains open for one-step binding and accurate failure copy; Task 2 remains open
  for a direct blocked worker-tool call. Full Chrome workflow preservation and the production
  go/no-go review also remain open.

Sources: [Claude CLI resume/fork behavior](https://code.claude.com/docs/en/cli-reference),
[Claude inbound control semantics](https://code.claude.com/docs/en/cross-session-messaging),
[Claude setting precedence](https://code.claude.com/docs/en/settings).
