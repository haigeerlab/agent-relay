# Spec: collaboration-messaging

## Objective

Provide an optional, private same-Mac mailbox through which ordinary Claude Code and native Codex
Desktop sessions can discover one another and exchange free-text technical messages without manual
copy-paste. The capability supplies a local runtime, narrow host adapters, session self-description,
and a one-step `collab` entry.

It is a communication bridge, not a task orchestrator. It does not infer project groups, assign
work, create Tickets or Issues, modify Git, or treat a message as authorization for another action.

Governance: the accepted Proposal and its attestation
(`spec/proposal-acceptances/collaboration-messaging-*.json`) cover the loopback XATS runtime only.
The experimental native transport below was added afterwards without a Proposal revision and was
brought into scope by the one-time registration of 2026-09-28
(`docs/decisions/2026-09-28-single-capability-map.md`). Promoting native to the default transport is a
new requirement and goes through the Proposal process. The evidence threshold for that Proposal and the
one-minor XATS retirement that follows it are fixed in `docs/decisions/2026-09-28-xats-sunset.md`.

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

### Experimental native-wake replacement (opt-in host selection)

- The MIT `WebisityStudio/claude-codex-mcp-bridge` runtime is pinned to commit
  `8f12c880cfdba73812b6ab7bc0f373fc467e0343`. Its explicit installer obtains that exact
  revision, installs locked dependencies without dependency scripts, and builds the local stdio
  server. It never calls the upstream general `setup`, which would add worker skills and edit host
  settings. An absent selector keeps XATS as the default. A separately authorized cutover selected
  native on one host and then passed ordinary two-host and dual-Chrome acceptance; this does not
  make it a general-release default.
- The optional runtime and SQLite mailbox live in an owner-only directory outside project
  worktrees. Both the mailbox path and the upstream process's XDG data home point inside that
  directory, so even its worker-schema startup side effect cannot write into another live bridge
  installation. Its status command and host adapter previews are read-only. Separate explicit
  `install-codex` / `install-claude` actions apply only this backend's host entries; they do not
  run during plugin installation or daily `collab`. Codex uses an exact communication-tool allowlist; Claude
  must receive exact worker-tool deny rules before its MCP server is enabled.
- Native wake uses observed private app IPC and is experimental, not a public host guarantee. A
  failed or held wake leaves durable unread mail; mailbox write, wake admission, read and explicit
  acknowledgement are separate outcomes. Agent names are same-user routing labels, not per-session
  security identities. No message grants authority to change code, Git, Issues or settings.
- A cutover requires an explicit old-mail and active-session preflight, one active mailbox per new
  session, preservation of the XATS archive and a rollback path that identifies unread new mail.
  The read-only XATS preflight counts deliverable unread mail without reading bodies or advancing
  cursors; registered identities are not evidence that a session is online, so their liveness
  still needs separate review. Its result is only a snapshot and cannot authorize cutover by itself.
  A matching read-only native preflight counts unacknowledged direct messages (including unknown
  recipient names) and broadcast deliveries under the pinned bridge's registration-time rule.
  It blocks rollback while mail or unresolved registered sessions remain; it neither acknowledges
  mail nor rewrites either selector or mailbox.
  The daily `collab` skill reads a private, read-only backend selector: an absent marker keeps XATS;
  a valid native marker requires a ready pinned runtime; a malformed marker or unavailable native
  runtime stops instead of silently falling back to XATS. No code in the selector writes the marker.
  A separate operator-only activation command requires a verified private XATS archive, matching
  reviewed inventory, a ready pinned native runtime, and explicit assertions that XATS is stopped
  and old sessions are closed. Those assertions cannot be inferred from registered identities or
  checked by the command. Installation and fragment generation never switch the daily backend;
  an absent marker keeps XATS selected.
  The operator-only rollback command first checks that the XATS mailbox is readable and the native
  mailbox has no registered sessions or unacknowledged deliveries. With explicit operator assertions
  that native sessions have stopped and XATS is running, it removes only the private selector marker;
  it retains the native mailbox and cannot independently verify either service assertion. A
  controlled live trial exercised this path and restored XATS after Claude Code access blocked
  cross-host acceptance. A later authorized retry passed the ordinary two-host exchange and kept
  native selected on that host; the old archive and native mailbox history were retained.

## Host and interaction contract

- Codex reads its authorization header through a local `http_headers_helper`. Native Codex Desktop
  remains in mailbox mode so ChatGPT in Chrome continues to work; the capability does not switch it
  to a managed app-server.
- Claude Code uses a fixed stdio-to-loopback bridge whose token exists only in the child process
  environment. User configuration and repository files contain no token.
- Claude Code's Chrome integration remains available alongside collaboration, including when its
  explicit launcher forwards `--chrome`; collaboration must not replace or disable `claude-in-chrome`.
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
- On XATS, native Codex Desktop does not promise active wake-up. Claude Code CLI may explicitly
  start in a tmux pane for XATS's short inbox hints; this is not a read acknowledgement or a
  default. Native wake passed one controlled host trial but depends on private app IPC, so it is
  not a general host guarantee. Claude channel wake is not offered; its experimental switches were removed.
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
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py status
python3 -B plugins/spec-guard/hooks/native_collaboration_runtime.py install  # explicit opt-in only
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py codex  # print only
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py claude # print only
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py install-codex  # explicit only
python3 -B plugins/spec-guard/hooks/native_collaboration_adapters.py install-claude # explicit only
python3 -B plugins/spec-guard/hooks/collaboration_backend.py          # read-only selector
python3 -B plugins/spec-guard/hooks/native_collaboration_activate.py --help  # operator-only switch
python3 -B plugins/spec-guard/hooks/native_collaboration_rollback.py --help  # operator-only rollback
python3 -B plugins/spec-guard/hooks/test_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_runtime.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_adapters.py
python3 -B plugins/spec-guard/hooks/test_collaboration_backend.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_activate.py
python3 -B plugins/spec-guard/hooks/test_native_collaboration_rollback.py
python3 -B plugins/spec-guard/hooks/test_native_collab_entry.py
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
plugins/spec-guard/hooks/native_collaboration_*.py      -> opt-in pinned runtime and host fragments
plugins/spec-guard/hooks/collaboration_backend.py        -> read-only one-mailbox selector
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
- Any wake-up enhancement must separately verify Claude Code in Chrome and ChatGPT in Chrome on
  their ordinary hosts; launcher argument tests alone do not prove browser integration works.
- Full repository validation and Codex smoke self-tests remain required before delivery.

## Boundaries

- Always: pin audited transport versions; use loopback and private files; distinguish accepted,
  delivered, read, and wake states; keep user-facing entry independent from operator actions.
- Ask first: initialize or start the runtime; enable launchd; install or replace host configuration;
  remove an exact stale identity; select Claude CLI tmux wake; change transport
  versions.
- Never: expose tokens; bind beyond loopback; silently alter Claude or Codex startup; disable
  ChatGPT in Chrome or Claude Code in Chrome; create project groups or automatic routing; translate
  a message into Git, Issue, Ticket, code, requirement, or authorization writes.

## Success criteria

- A newly started Claude Code or native Codex Desktop session joins with at most one `collab`
  invocation and becomes discoverable by a human-readable name or description.
- Two ordinary sessions in the same or different projects can exchange persistent messages and a
  reply without manual copy-paste or project-group setup.
- Runtime and host configuration contain no bearer token; unsafe paths, permissions, versions, or
  network binds fail closed.
- ChatGPT in Chrome and Claude Code in Chrome remain available, mailbox delivery is described
  honestly, and unavailable or ambiguous states produce one actionable next step without hidden
  side effects.

## Open questions

Cross-machine communication is deferred and requires a separate security design. Native Codex
Desktop wake passed isolated feasibility checks and one controlled ordinary-host trial, but is not
yet a generally supported default; remaining release gates are recorded in
[`../tasks/collaboration-messaging/native-wake-migration-plan.md`](../tasks/collaboration-messaging/native-wake-migration-plan.md).
A scheduled inbox check was explored but is not a supported daily-use action; its remaining
acceptance gaps are recorded in
[`../tasks/collaboration-messaging/codex-scheduled-inbox-acceptance-2026-09-25.md`](../tasks/collaboration-messaging/codex-scheduled-inbox-acceptance-2026-09-25.md).
