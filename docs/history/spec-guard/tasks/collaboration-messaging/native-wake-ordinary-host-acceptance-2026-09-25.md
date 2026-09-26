# Native ordinary-host acceptance — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Status: **two-way Claude Code ↔ Codex messaging and one idle Codex Desktop wake passed;
no transport cutover**. The ordinary one-invocation `collab` journey and an idle Claude wake
remain open.

## Host and tool surface

- The pinned native runtime at commit `8f12c880cfdba73812b6ab7bc0f373fc467e0343` was
  installed in owner-private storage. Its disposable-mailbox startup probe returned `ready`
  with 17 upstream tools. The live mailbox is separate from XATS and project worktrees.
- Codex's user MCP entry allows ten communication tools. A fresh Codex Desktop task loaded the
  native server as `ready`, saw those communication tools but no upstream worker, review or
  orchestration tools, and bound its own `CODEX_THREAD_ID` without asking the user for it.
  The older task that installed the entry did **not** acquire the new callable catalog after
  the app restart; a fresh task was necessary for this test.
- A fresh Claude Code CLI session connected to the same native server and called
  `bridge_agents`. Seven non-communication tools were denied before Claude's server was
  registered. The previous Codex configuration remained byte-identical before the appended
  native table; Claude's other settings and server entries remained structurally unchanged.
  Host configuration backups are kept privately outside the repository.

## Message and wake evidence

- The fresh Codex Desktop task registered only itself, had zero initial unread messages, and
  ended its first turn idle. A fresh Claude Code CLI session registered its own temporary
  identity and sent direct test message **1** to the Codex identity. The native wake receipt
  was `accepted`; this alone was not treated as proof of reading.
- Codex actually entered a new turn, read and acknowledged **1**, then replied with direct
  message **2**. The sender Claude process had exited, so the reply remained in its mailbox.
  Resuming the same Claude conversation read and acknowledged **2**. A subsequent read-only
  native inventory showed zero unacknowledged direct or broadcast deliveries.
- This proves the Codex idle wake and a two-way reply without manual message relay. It does
  **not** prove an idle Claude wake in this installed configuration: Claude was explicitly
  resumed to read the reply. Earlier isolated cross-host evidence is recorded separately.

## Chrome and cutover boundary

- A fresh `claude --chrome` session exposed 22 Chrome tools. The existing Codex Chrome
  extension could create and close one temporary `about:blank` tab. These are control-entry
  checks, not full simultaneous browser workflows; no existing user page or Chrome setting
  was changed.
- The active backend selector still returns `xats`. Its read-only inventory found 8 registered
  identities, 3 deliverable unread messages and unverified live sessions. The native mailbox
  has 2 temporary registered identities from this acceptance, with no unacknowledged mail.
  Neither inbox was cleared, no marker was written, and the old service was not stopped.
- The installed `collab` skill remains the pre-cutover XATS entry. This test used native host
  tools directly; the one-step native `collab` path is **not** accepted yet. Cutover remains
  blocked by the old unread mail and session review, irrespective of the successful smoke.
