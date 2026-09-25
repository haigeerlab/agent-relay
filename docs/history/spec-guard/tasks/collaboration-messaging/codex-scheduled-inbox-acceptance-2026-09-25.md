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

## Acceptance result

| Check | Result |
| --- | --- |
| Scheduled turn can access the collaboration MCP | Observed |
| Same conversation identity survives a later scheduled run | Observed |
| New message and empty inbox are distinguished | Observed |
| Empty run adds no text to the conversation | **Not met**: the second run emitted progress and a final status |
| Empty run causes no desktop or unread alert | Not established; conversation text alone does not prove an alert was sent |
| Message from an independent Claude or Codex peer is handled | Not tested; the message was self-sent |
| ChatGPT in Chrome remains usable during scheduled runs | Extension connection worked after the trial; actual use during the scheduled runs was not established |
| Paused schedule does not fire again | Pause was acknowledged by the host; no later-run observation yet |

## Decision

Task 1 is incomplete, so the `collab` skill must not expose an enable action yet. The trial proves
that scheduled turns can read this mailbox and reuse this identity, but it does not prove that an
empty run avoids an alert, handles an independent peer, or preserves Chrome functionality in use.
The existing manual mailbox flow remains the supported native Desktop path. Any further scheduled
trial needs explicit opt-in and must preserve the paused state when it ends.
This avoids shipping recurring model usage and empty-run conversation noise to every plugin user
before conditional alerts are demonstrated, while retaining the native App and ChatGPT in Chrome.
