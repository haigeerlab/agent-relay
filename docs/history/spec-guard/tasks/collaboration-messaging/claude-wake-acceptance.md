# Claude Code CLI wake acceptance — not passed

- Candidate runtime: pinned `cross-agent-teams-mcp@0.8.6`, host health reported running.
- Host: Claude Code CLI `2.1.281`; test used an empty temporary workspace.
- The opt-in launcher reached Claude Code's development-channel warning. The warning says not to
  use this option to run channels downloaded from the internet. The pinned XATS channel is a
  downloaded third-party package, so the test exited without confirming the prompt.
- No test message was sent. No unsolicited wake or reply was observed.
- The existing mailbox path and native Codex Desktop settings were not changed. ChatGPT in Chrome
  was not disabled.

Result: launcher contract tests pass, but active wake is **not verified** and is **not ready for
general-user enablement**. The next decision is an applicable official channel approval route or
a separately authorized, clearly development-only security exception.
