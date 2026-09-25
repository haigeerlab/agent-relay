# Spec: collaboration-messaging

## Objective

Provide an optional, private same-Mac mailbox through which ordinary Claude Code and native Codex
Desktop sessions can discover one another and exchange free-text technical messages without manual
copy-paste. The capability supplies a local runtime, narrow host adapters, session self-description,
and a one-step `collab` entry.

It is a communication bridge, not a task orchestrator. It does not infer project groups, assign
work, create Tickets or Issues, modify Git, or treat a message as authorization for another action.

## Runtime contract

- The transport is the audited MIT package `cross-agent-teams-mcp@0.8.6`; unpinned versions are
  rejected.
- The first release binds only to `127.0.0.1` on the same Mac. LAN, public, Tailscale, and
  cross-device modes require a separate security design.
- User data lives under a private `0700` directory. The bearer token is a regular `0600` file and
  never appears in project files, generated host configuration, process arguments, or diagnostics.
- Initialization, service enablement, host configuration, cleanup, and restart are explicit
  operator actions. Plugin installation and the daily collaboration entry perform none of them.
- XATS requires a team field, so every session uses the fixed internal namespace
  `spec-guard-local`. It is not a visible project group, router, ownership boundary, or permission
  model.

## Host and interaction contract

- Codex reads its authorization header through a local `http_headers_helper`. Native Codex Desktop
  remains in mailbox mode so ChatGPT in Chrome continues to work; the capability does not switch it
  to a managed app-server.
- Claude Code uses a fixed stdio-to-loopback bridge whose token exists only in the child process
  environment. User configuration and repository files contain no token.
- The daily user contract is `collab [optional alias]`, or equivalent natural language such as
  “加入本机联调”, “查看联调消息”, and “告诉可乐……”. Users do not provide the internal namespace,
  PID, agent type, project path, UUID, or MCP tool names.
- Every registration has a unique transport identity. Friendly aliases, project paths, host types,
  roles, and current work are voluntary self-description used by the Agent for human-name
  resolution only.
- A complete transport name is sent directly. A human alias or description is resolved from the
  visible directory: one candidate is used, zero candidates produce a not-joined explanation, and
  multiple candidates require one concise clarification. No fixed matcher, alias database, or
  project topology is introduced.

## Message and delivery contract

- Messages are free text with optional subjects and references. Message content never grants
  permission to modify code, Git, Issues, requirements, services, or user configuration.
- Mailbox persistence and real-time wake-up are separate facts. A successful write means the
  message entered the mailbox; only an explicit read acknowledgement means the recipient read it.
- Native Codex Desktop does not promise active wake-up. Claude Code CLI may explicitly start in a
  tmux pane for XATS's short inbox hints; this is not a read acknowledgement or a default. Claude
  channel wake remains a separate blocked preview enhancement.
- Normal session exit unregisters the current identity. Cleanup of an abandoned identity requires
  an explicitly supplied UUID and can delete neither messages nor processes.

## Commands

~~~text
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py status --format json
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py init
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py start
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py health --format json
python3 -B plugins/spec-guard/hooks/collaboration_runtime.py service-status --format json
python3 -B plugins/spec-guard/hooks/collaboration_adapters.py codex
python3 -B plugins/spec-guard/hooks/collaboration_adapters.py claude
python3 -B plugins/spec-guard/hooks/test_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_collab_entry.py
/bin/bash scripts/validate.sh
/bin/bash evals/codex-plugin-smoke.sh --selftest
~~~

## Project structure

~~~text
plugins/spec-guard/hooks/collaboration_runtime.py       -> private runtime lifecycle and recovery
plugins/spec-guard/hooks/collaboration_adapters.py      -> no-secret Claude and Codex configuration
plugins/spec-guard/hooks/collaboration_auth_header.py   -> Codex dynamic authorization header
plugins/spec-guard/hooks/collaboration_claude*.py       -> Claude launch and stdio bridge boundaries
plugins/spec-guard/skills/collab/SKILL.md               -> daily join, inbox, discovery, and send flow
plugins/spec-guard/skills/collaboration-ops/SKILL.md     -> explicit operator actions
plugins/spec-guard/references/collaboration-*.md         -> runtime and protocol contracts
plugins/spec-guard/hooks/test_collaboration_*.py         -> runtime and adapter regressions
plugins/spec-guard/hooks/test_collab_entry.py            -> user-facing entry contract
~~~

## Code style

Use standard-library Python, immutable contract constants, explicit CLI subcommands, structured
JSON results, and fail-closed validation. Security-sensitive defaults remain visible and pinned:

~~~python
PACKAGE_NAME = "cross-agent-teams-mcp"
PACKAGE_VERSION = "0.8.6"
LOCAL_NAMESPACE = "spec-guard-local"
DEFAULT_HOST = "127.0.0.1"
~~~

## Testing strategy

- Unit fixtures validate the pinned runtime, loopback-only bind, private permissions, symlink
  rejection, no-secret host configuration, launchd lifecycle, stale registration cleanup, and
  failure diagnostics without reading a real token or starting an uncontrolled daemon.
- Contract tests validate one-step joining, unique transport identities, Agent-driven name
  resolution, ambiguity handling, and the prohibition on implicit service or Git actions.
- Real-host acceptance covers ordinary Claude Code, Codex CLI, and native Codex Desktop in same-
  and different-project exchanges while preserving ChatGPT in Chrome.
- Full repository validation and Codex smoke self-tests remain required before delivery.

## Boundaries

- Always: pin audited transport versions; use loopback and private files; distinguish accepted,
  delivered, read, and wake states; keep user-facing entry independent from operator actions.
- Ask first: initialize or start the runtime; enable launchd; install or replace host configuration;
  remove an exact stale identity; select Claude CLI tmux wake or Claude channel wake; change transport
  versions.
- Never: expose tokens; bind beyond loopback; silently alter Claude or Codex startup; disable
  ChatGPT in Chrome; create project groups or automatic routing; translate a message into Git,
  Issue, Ticket, code, requirement, or authorization writes.

## Success criteria

- A newly started Claude Code or native Codex Desktop session joins with at most one `collab`
  invocation and becomes discoverable by a human-readable name or description.
- Two ordinary sessions in the same or different projects can exchange persistent messages and a
  reply without manual copy-paste or project-group setup.
- Runtime and host configuration contain no bearer token; unsafe paths, permissions, versions, or
  network binds fail closed.
- ChatGPT in Chrome remains available, mailbox delivery is described honestly, and unavailable or
  ambiguous states produce one actionable next step without hidden side effects.

## Open questions

Cross-machine communication and native Codex Desktop active wake-up are intentionally deferred and
require separate security and host-integration decisions. A scheduled inbox check was explored but
is not a supported daily-use action; its remaining acceptance gaps are recorded in
[`../tasks/collaboration-messaging/codex-scheduled-inbox-acceptance-2026-09-25.md`](../tasks/collaboration-messaging/codex-scheduled-inbox-acceptance-2026-09-25.md).
