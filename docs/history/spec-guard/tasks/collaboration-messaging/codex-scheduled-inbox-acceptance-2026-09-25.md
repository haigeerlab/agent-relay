# Codex Desktop scheduled inbox feasibility — 2026-09-25

This record contains no token, agent UUID, account data, message body, or full local path.

## Trial

- In an existing native Codex Desktop conversation, the current MCP session registered one
  `codex-desktop-native` identity. No app-server or alternate Desktop startup was introduced.
- With the user's permission, a temporary per-conversation, one-minute scheduled check was
  created with a limit of three runs. A harmless test message was placed in that identity's inbox
  without requesting a push wake.
- The first scheduled run read the test message through `get_inbox` using the existing identity.
  It did not register another identity, reply, or change files, Git, Tickets, or configuration.
- The second scheduled run used the same identity and returned an empty inbox. The temporary
  schedule was then paused before its planned third run.
- After the trial, the existing Chrome extension connection could still read an already-open
  local test tab. This was read-only and did not alter the browser or Desktop launch mode.
- In a second, explicitly permitted, two-run trial, a separate Claude Code CLI session registered
  its own temporary identity and sent one harmless message without a push wake. The first scheduled
  run read that message using the Codex conversation's existing identity; its message ID matched
  the sender's send result. This was not a self-send.
- The next scheduled run returned an empty inbox and produced no visible conversation text. The
  temporary schedule was paused immediately afterward. Its paused state was confirmed, and no
  further scheduled turn appeared during the following ten minutes. Both temporary identities
  were removed after the trial; the received message was retained.
- ChatGPT in Chrome opened and read a public test page after the second trial. This confirms the
  normal extension path still worked afterward, not that Chrome was used during a scheduled turn.

## Acceptance result

| Check | Result |
| --- | --- |
| Scheduled turn can access the collaboration MCP | Observed |
| Same conversation identity survives a later scheduled run | Observed |
| New message and empty inbox are distinguished | Observed |
| Empty run adds no text to the conversation | Mixed: the first trial emitted progress and a final status; the second trial's empty run emitted no visible text |
| Empty run causes no desktop or unread alert | Not established; conversation text alone does not prove an alert was sent |
| Message from an independent Claude or Codex peer is handled | Observed with a separate Claude Code CLI session |
| ChatGPT in Chrome remains usable during scheduled runs | Extension connection worked after both trials; actual use during a scheduled turn was not established |
| Paused schedule does not fire again | Paused state confirmed; no later turn observed during a ten-minute window |

## Decision

Task 1 is incomplete, so the `collab` skill must not expose an enable action yet. The trials prove
that scheduled turns can read this mailbox, reuse one identity, and handle an independent peer.
They do not prove that empty runs reliably avoid desktop alerts or that Chrome works concurrently
with a scheduled turn. The two empty-run outcomes also differ, so silence is not yet a stable claim.
The existing manual mailbox flow remains the supported native Desktop path. Any further scheduled
trial needs explicit opt-in and must preserve the paused state when it ends.
This avoids shipping recurring model usage and empty-run conversation noise to every plugin user
before conditional alerts are demonstrated, while retaining the native App and ChatGPT in Chrome.
