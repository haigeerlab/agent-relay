# Native Claude Code ↔ Codex wake smoke — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **isolated two-way real-host exchange passed; no production cutover**. This continued the
[Codex two-task smoke](native-wake-codex-smoke-2026-09-25.md) against the same pinned upstream
revision and private test mailbox. Existing Spec Guard XATS messaging remained the daily default.

## Host surface and identity

- Claude Code CLI v2.1.282 loaded a temporary user-scope MCP entry. Exact bare-name deny rules
  hid seven non-messaging tools. A fresh real Claude session's init catalog showed exactly the
  same ten communication tools as the Codex Desktop trial, with no worker, review, orchestration
  or retire tool. The trial did not install another plugin.
- A fresh background Claude Code session used `bridge_sessions` to identify its own conversation
  and `bridge_register` with `wake: "auto"` to bind only itself. Codex did not supply or claim its
  session ID. The Claude session then ended its first turn and was idle before the first send.
- Claude's first CLI config-write attempt reported success inside the sandbox but did not actually
  add a server. A real-host read-only check confirmed absence. The authorized user-scope add was
  then run outside that sandbox and independently verified as connected. The deny rules were
  installed and checked *before* this add, so the extra upstream tools were not exposed during
  the trial.

## Two-way message evidence

- Codex sent message **4** by registered name to the idle Claude session. The initial wake receipt
  was `unknown` (`Ping submitted; awaiting Claude receipt`), not a false assertion of delivery.
  Claude entered a new turn, read and acknowledged message 4, and replied with message **5**.
  Codex read and acknowledged 5. The separate acknowledgement timestamp showed that 4 was
  handled even though the wake receipt's `read` detail still said work was not acknowledged.
- Codex next sent coordination message **6** to idle Claude. Claude read and acknowledged 6, then
  sent direct message **7** to the *other* idle Codex Desktop task using its registered name, not
  a task ID. The bridge reported `accepted` (`Codex confirmed a new turn`). That Codex task woke,
  read and acknowledged only 7, and replied with **9**. Claude read and acknowledged 9, then
  reported the completed loop in **10**; Codex acknowledged Claude's progress report **8** and
  result 10. All three trial agents ended with zero unread messages.
- These messages were test instructions and results only. Neither peer treated a message as
  authority to change code, Git, issues, settings, or services.

## Cleanup and remaining boundary

- The temporary Claude background session was stopped. The trial MCP entry and its seven deny
  rules were removed. Claude settings matched their pre-trial backup byte-for-byte; its MCP server
  map and Chrome-related settings matched the pre-trial backup structurally. Other Claude CLI
  runtime metadata changed during the test and was deliberately not overwritten with an old
  whole-file backup.
- Codex's exact whole-file removal guard refused to run because its user config had changed in
  the meantime. Only the trial stanza at the end of that file was removed; every earlier line was
  preserved. A fresh `codex mcp get` no longer found the trial entry. On follow-up, all three
  trial inboxes had zero unread mail. Six exact trial Node subprocesses were still loaded by
  Codex Desktop; they were stopped with normal termination, and none restarted. The owner-private
  temporary directory containing the isolated SQLite mailbox, source checkout and config backups
  was then permanently deleted. No existing XATS data or project source was removed.
- A fresh `claude --chrome` CLI session still exposed the Claude Code in Chrome tool catalog.
  Codex's existing Chrome extension connection could open, inspect and close a new `about:blank`
  tab without touching an existing user page. These are entry/control smoke checks, not a
  simultaneous end-to-end Chrome workflow test. No Chrome setting or extension was changed.
- This did **not** exercise busy, absent or permission-held Claude targets, forked sessions,
  multiple-project discovery or the full ChatGPT in Chrome / Claude Code in Chrome workflows.
  Functional Chrome preservation still needs its own acceptance test. The bridge's stale `read`
  detail and broad upstream server instructions also remain integration concerns.

Tasks 1 and 2 therefore remain open. This evidence supports a narrowly scoped next test, not
switching users from XATS or claiming the one-command Spec Guard experience is implemented.
