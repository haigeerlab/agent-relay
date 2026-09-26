# Native wake communication surface decision — 2026-09-25

Plan: [`native-wake-migration-plan.md`](native-wake-migration-plan.md)

Decision: **Task 2 passes for the chosen same-user cooperative boundary.** This is a host
tool-exposure decision, not an access-control certification or a product cutover.

## Evidence and scope

- The pinned MIT bridge revision is `8f12c880cfdba73812b6ab7bc0f373fc467e0343`.
  Its Node requirement, 70 passing real-host tests and zero high-severity dependency
  findings are recorded in the [surface preflight](native-wake-surface-preflight-2026-09-25.md).
  The fresh trial used an owner-only `0700` directory, a `0600` SQLite mailbox and a stdio
  MCP command; no HTTP listener was configured. This is private local storage, not isolation
  from other processes owned by the same user.
- Ordinary Codex Desktop exposed only the configured eight communication tools in the
  [fresh idle-wake trial](native-wake-desktop-idle-trial-2026-09-25.md). An earlier Codex
  trial and fresh Claude Code session each exposed only ten communication tools, with
  worker/review/orchestration tools absent from their model-callable catalogs. Codex documents
  `enabled_tools` as an allowlist; Claude documents that bare-name deny rules remove a tool
  from the model context and prevent its use.
- A direct raw call to a hidden upstream worker tool was **not** tested. The upstream server
  still registers those tools, so a separate same-user client could invoke them outside the
  filtered hosts. The chosen trust contract explicitly does not defend against that client.
  The prior direct-call test is therefore follow-up hardening, not a gate for preventing
  accidental use through ordinary Spec Guard host sessions. If untrusted local processes
  become in scope, this decision is insufficient and the integration must stop for a new
  server-side restriction or facade review.

## Remaining decision

The technical feasibility gates now pass, but XATS remains the supported default. The operator
must still review private app IPC and pinned-upstream maintenance risk before amending the
accepted Spec. Task 6 must prove one-invocation `collab`; the later cutover requires explicit
old-mail and rollback checks. No runtime, user configuration or production mailbox was changed
for this decision.

The proposed risk acceptance is limited: native wake relies on private host IPC and can fail
after a host update; durable unread mail must remain available and the adapter must report
`held`, `offline` or unknown outcomes without claiming delivery. The upstream revision stays
pinned and requires a new audit before an update. The prior Chrome entry smokes did not prove
complete simultaneous Chrome workflows, which remain a final acceptance condition. Recommend
proceeding to a reviewed Spec amendment for an **experimental** wake adapter, not enabling a
new production mailbox or replacing XATS yet.

Sources: [Codex MCP tool selection](https://learn.chatgpt.com/docs/extend/mcp),
[Claude permission rules](https://code.claude.com/docs/en/permissions).
