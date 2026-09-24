# Collaboration entry acceptance — 2026-09-24

This record contains only non-secret host and message metadata. It does not record the runtime
token, agent UUIDs, process IDs, full local paths, account details, or message contents.

## Candidate under test

- Spec Guard candidate: `0.17.0` from the local marketplace.
- Collaboration runtime: `cross-agent-teams-mcp@0.8.6`, healthy on loopback.
- Codex collaboration MCP: enabled through the configured HTTP header helper.
- Claude collaboration MCP: connected through the configured stdio bridge.
- Codex Chrome integration: still installed and enabled; no managed Codex app-server was introduced.

## Real-host checks

1. A normal interactive Claude Code session loaded `spec-guard:collab`, joined with a friendly
   alias, generated a unique suffixed registration name, read its inbox, and listed peers.
2. A fresh Codex CLI session loaded the same installed skill, joined with a unique suffixed name,
   and sent a message to Claude by its complete registration name.
3. The same live Claude session read the Codex message and replied using the sender identity carried
   by the message. The local mailbox contained both directions in order.
4. A second fresh Codex CLI session received only a human-facing recipient description. It read the
   directory, found exactly one matching session, and delivered the message without a hard-coded
   registration name.
5. Both hosts reported mailbox acceptance separately from read or wake state. Neither claimed that
   an offline or mailbox-only peer had been actively awakened.
6. Repository status stayed clean throughout the exchange; the collaboration entry performed no
   file, Git, Issue, or Ticket write.
7. After a normal Codex Desktop restart, a new native Desktop task discovered `spec-guard:collab`,
   generated a readable automatic name with a unique suffix, registered itself, read its inbox, and
   listed the same local directory.
8. The restarted Desktop sent a message to the unique friendly-name match. A fresh Claude Code
   session replied, and the same Desktop MCP session read the reply from its inbox.
9. ChatGPT in Chrome remained available. The test did not start or connect a managed Codex
   app-server.
10. A fresh Claude Code session in a separate fixture repository joined with its own friendly name
    and sent a message to the native Desktop session. The Desktop read the message from the same
    mailbox, confirming that project paths are descriptive metadata rather than communication
    boundaries.
11. A fresh Codex CLI session exercised both safe lookup edges. A nonexistent friendly name matched
    zero sessions and produced no delivery; an ambiguous description matched multiple sessions,
    asked one concise clarification, and did not call `send_message`. The mailbox count stayed
    unchanged across both checks.
12. A temporary Codex CLI process pointed only its own collaboration MCP endpoint at an unreachable
    loopback port. The refreshed `collab` entry attributed the failure to that process-local
    endpoint, refused to treat it as proof that the background service was offline, and gave one
    next action: open a session without the temporary override. It made no configuration, service,
    Git, Issue, or Ticket write. A separate host-side health check still reported the daemon as
    running.

## Result

No local entry or identity acceptance item remains. Proposal acceptance and promotion were completed
through the separate protected mainline workflow and were not inferred from these host checks.
