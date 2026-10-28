# agent-relay

[简体中文](README.md) | English

Lets Claude Code and Codex sessions on **the same Mac** pass messages to each other, find each other by name, and,
within a limited authorization you give, create and continue review or development sessions. No copying and pasting
between sessions, and no workflow plugin required.

agent-relay started as an optional collaboration feature of [Spec Guard](https://github.com/haigeerlab/spec-guard-plugin)
and is now a standalone plugin: a project that only needs its sessions to talk to each other (a design project, for
example) needs nothing else.

> Status: 0.9.4 (interface 2.10; Spec Guard is not needed, but installed alongside it must be 0.56.0 or later). Changes
> and upgrade steps are in [CHANGELOG.md](CHANGELOG.md) (written in Chinese); the issues that still apply are under
> "[Known issues](#known-issues)" below; the goal of each item is in the "hardening target" column of
> [docs/collaboration-interface.md](docs/collaboration-interface.md).
>
> Once the plugin is installed, tell any session "**check the agent-relay status**" and it tells you which steps are
> left (see "[Quick start](#quick-start)").

## What it does

| Capability | Description | Entry point |
|---|---|---|
| Collaboration mailbox | Sessions on the same Mac send and reply to messages; across hosts (Claude Code ↔ Codex) they go through a private local bridge | `collab` skill; Claude Code also has `/agent-relay:collaboration` |
| Session routing | Reach another session by its name; on the same host the host's own messaging is preferred (Claude Code `SendMessage`, Codex App threads), the mailbox only across hosts | `session-routing` skill |
| Cross-host session delegation | One sentence makes the current Claude Code create a Codex review session, or Codex create a Claude Code development session (only these two directions; no same-host delegation); by default a limited authorization for one task in one new session, with the result coming back to the session that asked (see "[Delegation end to end](#delegation-end-to-end)"). When the delegate plugin is installed in Claude Code, "send it to Codex" goes to it and this is only the fallback | `session-delegation` skill |
| Runtime management | Inspect and, with your consent, install the local mailbox runtime, attach or detach host configuration, retire identities that ended | `collaboration-ops` skill |

## Requirements

- macOS; Node.js 22.5 or later (the mailbox runtime uses the built-in `node:sqlite`, available from 22.5.0); Python 3.9
  to 3.14 (macOS's own `/usr/bin/python3` 3.9 works; the full test suite has run on 3.9, 3.10 and 3.14).
- agent-relay's commands use the node pinned in the host entries, not the current shell's PATH; below 22.5.0 it is
  refused (`node-too-old`) before any host is touched. The selection order is in the
  [runtime notes](plugins/agent-relay/references/collaboration-runtime.md).
- Claude Code and/or Codex (App or CLI).

## Quick start

### 1. Install the plugin

Claude Code:

```bash
claude plugin marketplace add haigeerlab/agent-relay
claude plugin install agent-relay@agent-relay-marketplace
```

Codex (pinned to the released version):

```bash
codex plugin marketplace add haigeerlab/agent-relay --ref v0.9.4
codex plugin add agent-relay@agent-relay-marketplace
```

For development you can replace `haigeerlab/agent-relay` above with the path of a local clone. For both hosts to talk,
install it on both.

### 2. Set up: tell a session "check the agent-relay status"

Installing the plugin only loads its skills and command. It does **not** create the runtime or change host
configuration. After that sentence the agent checks read-only, tells you which steps are needed, and waits for your
consent at each one:

1. Install the private runtime: from the bridge copy shipped in the plugin, verified against its hashes, it builds the
   runtime and a private mailbox in `~/.agent-relay/runtime/` (readable and writable only by you). No git is needed;
   `npm` dependencies are still installed from the npm registry by the lockfile, so this step needs network.
2. Attach the hosts: register the user-level MCP server `agent-relay` for Claude Code, or append
   `[mcp_servers.agent_relay]` to the Codex configuration. Attaching Codex writes `approval_mode = "approve"` for the
   10 mailbox tools (reading, replying and acknowledging show no card) and lists the 10 approval tables written to
   `~/.codex/config.toml` (`[mcp_servers.agent_relay.tools.<tool>]`); an existing install adds them with
   `install-codex --approve-mailbox-tools`, which lists only the ones added.

Then **restart the sessions that were already open** so they see the mailbox tools. Run
`python3 -B <plugin dir>/hooks/native_collaboration_runtime.py doctor` (plugin directory: see
"[Finding the plugin directory](#finding-the-plugin-directory)"); every item should be ok, a `warn` names its next
step, and the exit code is 1 when anything fails.

### 3. Once per project: trust it

- Claude Code: the trust dialog when it first opens a project **preselects "No, exit"**; pressing Enter quits, so select
  "Yes" first.
- Codex: when adding the project in the App, choose to trust the folder.

### 4. Optional: stop Claude Code asking for every mailbox tool

In Claude Code the 10 mailbox tools ask for confirmation on every call by default. To allow them all at once, run
`python3 -B <plugin dir>/hooks/native_collaboration_adapters.py claude-allow-rules` and add the 10 exact rules it prints
to `permissions.allow` in `~/.claude/settings.json`. Whether to add them is your choice; agent-relay never edits that
file; Codex is pre-approved when attached.

### 5. One sentence per session: join

Tell the session "**join local collaboration and allow wake, use the name X**" (in Chinese: "加入本机联调并允许唤醒，名字用 X";
any language works).

- Without "allow wake", the session is not woken when another session sends it a message; it has to check its inbox.
- Any permission mode can join, including Claude's auto mode; the exception is **Bypass permissions**, which holds
  incoming pings until they expire (see "[Authorization and safety](#authorization-and-safety)").
- When the name is held by an old session that has stopped, choosing another name is simplest; only if you insist on
  the original name do you need to agree to a takeover.

### 6. What you should see after the first message

In Claude Code, say "tell X in Codex: the home page draft is at `designs/home.fig`, please confirm":

1. The sending session finds X by name, sends the message, and tells you its id (`#id`) and delivery state: usually
   `queued` first, `accepted` once it is delivered. A message to a Claude session often stays `unknown` until the
   recipient reads it and it becomes `accepted`; that is normal, **do not resend** (see
   "[Troubleshooting](#troubleshooting)").
2. If the recipient is bound for wake it is woken, reads the message, handles it and acknowledges it; when your message
   is a question or a work request it answers you with `replyTo`.
3. The answer wakes the sending session (if it is bound for wake too), or shows up the next time you ask to "show
   collaboration messages".
4. If the send result carries a warning, follow it: for example the recipient is not bound for wake, has stopped, or
   waits for an approval.

Between sessions on the same host (Claude ↔ Claude, Codex ↔ Codex) the host's own messaging is preferred and the
mailbox is not used, so there is no message id.

## Everyday use

Just say it in natural language; no tool names or internal IDs to remember:

- "Join local collaboration", "show collaboration messages", "which sessions are there" → join the mailbox, read the
  inbox and the directory.
- "Tell the session of the design project in Codex: the home page draft is at `designs/home.fig`, please confirm" →
  finds the session by name and sends the message; when several sessions share the name you get short ids to choose
  from.
- "Reply to that session" → replies to the most recent message.
- "Create a Codex review of these changes" → creates a read-only review session; the result comes back to the current
  session (see "[Delegation end to end](#delegation-end-to-end)").
- "Continue that session", "stop that review" → second round in the same session, stop.
- "Which of my requests has nobody answered", "who am I waiting for" → the requests sent through the mailbox and
  marked as expecting a reply (`expectsReply`) that have no reply yet, oldest first, each with how long it has waited
  and the recipient's state (`bridge_outbox` with `awaitingReply`); "who owes a reply", "what do others wait for from
  me" → per session, how many requests others wait for it to answer and when the oldest was sent (`owesReplies` in
  `bridge_agents`). Sessions mark their own questions and work requests; the recipient answers with `replyTo` when
  done, and an ack alone does not count; plain notices are not marked and never appear here.
- "Who am I in the mailbox" → this session's identity, host, session title and project (`whoami` of `bridge_sessions`).
- "What happened to that message", "wait for its reply" → check a message's state by id, or wait until it is
  acknowledged, answered, failed or expired (`bridge_wake_status` / `bridge_wait` with `messageId`; waiting
  acknowledges nothing on anyone's behalf).
- Long messages (`long-messages`): a send returns only the id and length, never the body; when the recipient cannot read
  it in one page, the result's `continue` line gives the next `bridge_inbox` arguments (`messageId`, `bodyOffset`), so
  it is read piece by piece without Bash. Each page is about 12k tokens, within the hosts' output limits for Chinese and
  English alike.
- Long bodies, or bodies with `$`, backticks or quotes → write them to a file first and send with `bodyFile`; the
  content arrives byte for byte (absolute path, a regular file you own, at most 256 KiB, UTF-8).
- "Check the agent-relay status" → `native_collaboration_runtime.py doctor`: a read-only check of the runtime, mailbox,
  host attachment, Codex approval mode and wake-bound sessions (it points out a session stuck waiting for input), each
  item with a next step; exit code 1 when anything fails.
- "Retire identity X" → a finished name leaves the directory and its history is kept. Once you name it or approve the
  list, the agent runs `python3 -B <plugin dir>/hooks/native_collaboration_retire.py --name <name> --confirm-retire`
  (`--note <text>` optional); it refuses while the identity still has messages it has not acknowledged (expired ones do
  not count), so read and acknowledge them first. Sessions cannot retire identities.
- Reusing a retired name → registering it is refused; with your consent the session registers with
  `reactivate: true`, or picks a new name.
- Self-test and version: `native_collaboration_runtime.py probe` starts the runtime against disposable data and checks
  that it answers, without touching the real mailbox; `status` reports read-only whether the runtime is ready;
  `~/.agent-relay/bin/agent-relay --version` prints the runtime's version.

### The ten mailbox tools

You do not call them yourself; the agent picks them from what you say. Their names appear in permission prompts,
`claude-allow-rules` and send results (in Claude Code the full name is `mcp__agent-relay__<tool>`). Parameters and
results are in the [interface document](docs/collaboration-interface.md), §2.1.

| Tool | What it does |
|---|---|
| `bridge_register` | Register this session's name, optionally binding wake (`wake`); `takeover` to take over another session's name, `reactivate` to reuse a retired one |
| `bridge_send` | Send: `replyTo` answers a message, `expectsReply` marks a request, `idempotencyKey` prevents duplicates, `bodyFile` reads the body from a file |
| `bridge_inbox` | Read the inbox (oldest first, long messages in pages); only the identity itself records a read |
| `bridge_ack` | Mark handled; history kept |
| `bridge_outbox` | How far your sent messages got; with `awaitingReply`, only requests still waiting for an answer |
| `bridge_agents` | Directory: each session's state, unhandled messages and owed replies |
| `bridge_sessions` | Live Claude sessions on this Mac, and "who am I" (`whoami`) |
| `bridge_wake_status` | Wake records; with `messageId`, one message's progress |
| `bridge_thread` | A whole conversation by thread |
| `bridge_wait` | Wait in the current turn for a new message, or for one message's outcome |

## Delegation end to end

Delegation means one side opens a new limited session on the other host to do work. Only Claude Code → Codex and
Codex → Claude Code exist; same-host delegation is refused (`same-host-unsupported`): open a new session on that host
directly.

### Before you start

- **The session that starts the delegation joins and allows wake first**, so the result comes back to it
  automatically. Without that, or in Bypass mode, the delegation is still created, but its result is marked
  `recipient-unavailable` and does not wake you; the agent tells you to join first.
- **When the target is Claude Code**, the target project must have been trusted, and its `.claude/settings.json` or
  `.claude/settings.local.json` needs an allow for the 10 mailbox tools (`mcp__agent-relay__bridge_*`). The user-level
  `~/.claude/settings.json` alone does not count, because a delegated session reads only the project's two settings
  files by default, unless you use "load my user environment" below. A read-only review needs no extra allow for
  `Read`/`Grep`/`Glob`; development additionally needs `Edit`, `Write` and `Bash(...)` rules that fit the task.
  agent-relay reads and reuses these project-level rules but never writes them.
- To check beforehand, ask "check the permissions for a delegation": the agent runs the read-only `permissions`, which
  lists the allow rules needed, the settings files actually read and what is missing, and writes nothing.

### How a delegation goes

1. You say "create a Codex review of these changes". That sentence is itself the authorization for one task in one
   session.
2. The agent shows a **non-blocking creation notice**: target host, project short name, baseline short id, permission
   (`safe-review`, read-only, by default), count 1 and expiry (8 hours by default), and creates it without asking
   again. To be asked every time, say "ask me before every start".
3. The target session works in its own host; when it needs a permission its own settings lack, it asks you as usual.
4. When done, the target sends a short result through the mailbox to the session that asked, which is woken and reads
   it. `resultDelivery` of `enqueued` means only that it was written to the mailbox, not that your side has read it;
   `pending`, `missing`, `unverified` and `recipient-unavailable` each mean something else, and the agent reports them
   as they are.
5. Afterwards you can say "continue that session" (a second round in the same session), "how is that review doing" or
   "stop that review". When names clash, the agent shows a short distinguishing id to choose.

Two permission levels: `safe-review` (the default) only reads the chosen project and diff and runs local read-only
checks; `bounded-development` writes source and runs checks only in a clean, separate worktree you choose. Push,
merge, release, remote tracker writes, deletion and global configuration each need a separate authorization.

### When delegation is held

When a prerequisite is missing, delegation does not start a half-working session: it shows `held` and the smallest
next step. agent-relay does not change your settings, accept trust for you or switch to bypass; fix it and ask again.

| Shown | Cause | Fix |
|---|---|---|
| `held/project-allow-rules` | The target project lacks the allow rules for the mailbox tools | Add the rules it lists to the target project's `.claude/settings.json` or `.claude/settings.local.json` |
| `held/project-trust` | You have not trusted the target project in Claude Code yet | Open the project in Claude Code and choose "Yes" in the trust dialog |
| `held/mcp-project-approval` | The target project has not accepted this temporary MCP yet | Approve it in Claude Code as prompted |
| `held/host-permission-prompt` | The host still wants a manual permission decision | Handle that permission as prompted |
| `held/identity-retired` | The mailbox identity of a Codex delegation was retired, so a follow-up's result could not come back; nothing was sent | Create a new delegation, or decide whether to restore that name |

### Options

- **Review only some files**: say "review only `src/` and `README.md`"; the scope goes into the session's constraints
  and the result ends with the files actually read. A Claude Code session also has a hook that refuses reads outside
  the scope; a Codex session relies on the constraints alone. Read-only reviews only.
- **Load the user environment** (Codex → Claude Code only, off by default): say "load my user environment" and the
  delegated Claude Code session brings your own settings, plugins and skills; user-level allow rules then count, and
  the allow list must include `Skill`; if it is missing you see `held` and the rule to add before anything starts.
- **Clean up stuck delegation records**: say "clean up stuck delegations"; the agent first lists the records read-only
  (name, short id, state, whether the host still has it), and only after you confirm marks the ones you chose as
  cancelled. It changes records only, deletes nothing and touches no host.

## Troubleshooting

**Mailbox tools fail with `Transport closed`**
This session's connection to the mailbox is gone, usually because the runtime was just upgraded or the bridge process
was ended; retrying will not help. Codex: quit the ChatGPT app completely with ⌘Q and reopen it. Claude Code: open a
new session. Once connected, register the original name again before carrying on.

**A message stays `unknown`**
When a wake's outcome is unclear it is marked `unknown`; the bridge **never resends automatically**, and neither should
you. For a Claude recipient that does not hold the ping, Claude Code usually sends no receipt, so the message stays
`unknown` until the recipient reads it and it becomes `accepted`; that is normal. To follow it, ask "what happened to
that message" or "wait for its reply".

**A send reports an error**
An error from `bridge_send` means the message was not saved. When a step after saving fails (a busy database, for
example), it does not report an error: it returns the stored id with a warning "Saved as #id; … Do not send it
again." and the wake is retried in the background.

**Pings to a Claude session are held and then expire**
The recipient is in Bypass permissions: Claude Code holds pings for your approval and the desktop app has no place to
approve them. See the first item of "[Authorization and safety](#authorization-and-safety)". A session that has just
started also holds pings for a few seconds and then releases them; that is not Bypass. The bridge tells the sender only
after a hold has lasted 90 seconds; do not resend while a message is held.

**A delegation shows `held/...`**
See "[When delegation is held](#when-delegation-is-held)".

**A Codex session shows `not-loaded`**
The ChatGPT app has not opened that task since it started. Open it in ChatGPT and the message arrives; it is not a
connection or identity fault. Right after the app starts, while it loads many tasks, a reply slower than 2 seconds also
shows `not-loaded` for a moment; the next call corrects it.

**A send or ack is refused because the name is not registered by this session, or is recorded for a Codex task**
After a bridge restart (for Codex also after the ChatGPT app restarts or a long-idle task is reopened), the session
registers its original name once again and repeats the step. No takeover is needed.

**A Claude session is not running and messages do not go in**
The Claude desktop app stops the process of an idle session. Messages stay queued and you are notified after five
minutes; opening the session delivers them. The sender sees `pendingReason: offline` in `bridge_outbox`.

**A session waits for your approval**
The directory says so. When a Claude session sits on an approval prompt, this Mac shows a notice; when a Codex task
(one the ChatGPT app has loaded) sits on an approval card or waits for your answer, the directory reports
`waiting-approval` or `waiting-input`, but no notice is shown: handle it in the ChatGPT app.

**A new parameter is refused after an upgrade (`expected boolean`)**
An open session keeps the old tool definitions. Open a new Claude Code session or a new Codex task.

**No notices appear**
On most Macs `osascript` notices are silently dropped. Install terminal-notifier and allow it on its first notice;
`doctor --test-notification` shows a test notice. See [Notices and delivery details](docs/notifications.en.md).

**Anything else**
Run `doctor` first; it gives a next step for every item. The full troubleshooting order is in the
[runtime notes](plugins/agent-relay/references/collaboration-runtime.md), "Troubleshooting order".

## Authorization and safety

> **A Claude session in Bypass mode cannot be woken.** In Bypass permissions, Claude Code holds pings from other
> sessions for your approval; the desktop app has no place to approve them, so they expire. Binding wake still works,
> but to actually be woken you set Claude Code's `crossSessionInbound` to `"accept"` yourself, or use another
> permission mode. See [BACKGROUND-WAKE.md](plugins/agent-relay/bridge/docs/BACKGROUND-WAKE.md), "Why Claude pings
> expire". agent-relay will not change it for you.

- **No wake by default**: joining registers with `wake: null`, so an idle session is not woken by others; only when you
  ask explicitly is the current session bound for wake.
- **A woken session runs under its own permissions** (`wake-any-mode`): what the woken turn may do is decided entirely
  by that session's settings; the bridge does not change, lower or approve anything, and a session that needs more asks
  you as usual. **Risk**: with Codex on "approve for me" or Claude in auto mode, the woken turn's actions are approved
  by that session's automatic reviewer or classifier, not necessarily by you — that is the mode you chose for it. The
  approval selector in the Codex App governs only the turns you start and is not written to `config.toml`; a woken turn
  runs with the task's current approval and sandbox settings.
- **Messages are only data**: text in the mailbox never authorizes changes to code, Git, configuration or remote
  systems.
- **Item by item consent**: setting up the runtime, changing host configuration, joining a new identity and widening
  permissions each need your consent.
- **No automatic changes** to project or global permissions; it does not accept project trust or the first MCP approval
  for you and does not turn on bypass mode. When a prerequisite is missing it shows `held` and the smallest next step.
  To avoid repeated permission prompts you can preconfigure project-level allow rules in the target project's
  `.claude/settings.json` (see "[Delegation end to end](#delegation-end-to-end)").
- **An identity belongs to the session that registered it**: sending (`from`), ack and the auto-acknowledging
  `bridge_wait` accept only names this session registered, otherwise they refuse with a next step. A Claude session's
  name survives a bridge restart, while a Codex session registers again with the same thread id after a bridge restart.
  Another session's name or wake binding can be taken over with `takeover: true` only with your agreement; a session
  can bind wake only for itself. Only a message's recipient can reply to it (broadcasts: anyone except the sender;
  automatic bridge notices cannot be replied to). This guards against mistakes and mix-ups, not malicious local
  processes.
- **You are told when a session waits for you** (`presence-and-approval`): the directory says whether each session is
  running, stopped, waiting for approval, waiting for input, not loaded (`not-loaded`, Codex only) or unknown; sending
  to a session that waits for approval or has stopped gives the sender a warning.
- **Notices**: when a Claude session waits for your approval, Codex cannot receive a message, or a stopped Claude
  session cannot take one, this Mac shows a notice, at most one each time. The body of a Codex notice is a
  **single-line preview of at most the first 60 characters** of the message, which appears on the lock screen and
  shared screens; a `notify-preview.off` file in the mailbox directory (`~/.agent-relay/runtime/mailbox/`) leaves only
  ids, and `notify.off` turns notices off. A notice approves nothing. The channel, click actions and the "Automation"
  permission are in [Notices and delivery details](docs/notifications.en.md). The place you can always see is the
  **waiting list**: ask any session "which messages are waiting for Codex", or run doctor and read `codex-waiting`.
- **The sender is warned when the recipient cannot be pinged**: when the recipient is neither bound for wake nor known
  to be on a host (for example Codex registered with `wake: null`), the send result carries a warning that the recipient
  has to check its inbox itself. No notice is shown, because there is no one known to tell.
- **No "exactly once" promise**: every direct message has a delivery state (`queued`, `sending`, `accepted`, `failed`,
  `unknown`, `expired`); when unclear it is `unknown` and never resent automatically; a message still queued after its
  timeout (24 hours by default) becomes `expired` and the sender is notified. The per-recipient cap, `idempotencyKey`
  and reply rules are in [Notices and delivery details](docs/notifications.en.md#delivery) and the interface document,
  §6.

## Known issues

Only the ones that still apply; what each release said at the time is in [CHANGELOG.md](CHANGELOG.md).

- **A script identity cannot acknowledge the messages it receives** (found in 0.9.3): the CLI has no `inbox` or `ack`
  command, and a session's `bridge_ack` for it is refused. Messages to a script identity stay until they expire (24
  hours by default), and until then the identity cannot be retired. A script cannot read an answer's body either, so
  scripts should send notices and leave out `--expects-reply`.
- **Messages to a Claude session often stay `unknown`** (0.9.4 acceptance): when the recipient does not hold the ping,
  Claude Code usually sends no receipt, so it becomes `accepted` only once the recipient reads it. Do not resend.
- **A stopped Claude session cannot be woken** (0.9.0): no sender can wake a session the Claude desktop app stopped;
  messages stay queued and you are notified after five minutes.
- **A Codex task's first mailbox call after the ChatGPT app restarts is refused once** (0.7.1): the bridge cannot tell
  which Codex task calls it; the session registers its original name again as the refusal says and repeats the call.
- **A task the ChatGPT app has not opened since it restarted reports `not-loaded`** (0.8.3), not a waiting state.
- **Codex waiting states were checked on the real host only for command approvals and questions** (0.8.4): file
  changes, permission requests and MCP tool questions are covered by unit tests only.
- **Open requests are not closed automatically** (0.8.0): the recipient closes them with `alsoAnswers`, or the sender
  with `withdraws`; trust `closed` in the result.
- **launchd has not been tried on the real host yet** (0.9.0).

## What it does not do

- It does not cross machines; it only works on one Mac. It offers no network service and never exposes the mailbox to
  other machines.
- It is not a tracker or job dispatcher: no project groups, claiming or scheduling.
- It carries no development workflow (Specs, plans, phase hints and so on belong to Spec Guard).
- It does not promise "exactly once"; "accepted by the host" does not mean "handled by the recipient" (interface
  document §6).

## Scripts and launchd

Scripts and launchd jobs (PATH only `/usr/bin:/bin`, no access to `~/Documents`) read the mailbox and send through
`~/.agent-relay/bin/agent-relay`, written by `install` and `upgrade` with absolute node and runtime paths. `agents`,
`outbox <name>` and `sessions` are read-only and print what the matching MCP tool returns; `send` sends only as a
script identity the user registered, with the body from `--body-file` or stdin:

```bash
~/.agent-relay/bin/agent-relay register-script-identity my-patrol --confirm
printf 'patrol: #12 is still unhandled' | ~/.agent-relay/bin/agent-relay send --from my-patrol --to some-agent
```

Commands, exit codes and wake limits are in the interface document, §2.4. A script identity cannot acknowledge what it
receives or read an answer's body: see "[Known issues](#known-issues)".

## Updating and upgrading

### Updating the plugin

A Claude Code session decides which copy of the plugin to use **when it starts**, and keeps using it: sessions already
open, the app closed and reopened, and resumed sessions all keep the old copy. After updating, **open a new session**
(including the desktop app's Code tab) to use the new version. (The copy a new session loads was measured on this Mac
on 2026-10-10; "a resumed session keeps the old copy" is one case observed by the coordinator.) The mailbox tool
parameter definitions behave the same way: an open Claude Code session does not get new parameters by reconnecting
MCP (measured on this Mac after the 0.7.0 upgrade), and a new parameter is refused (`expected boolean`); to use new
parameters, open a new Claude Code session or a new Codex task (whether an old Codex task gets them after the app is
reopened was not measured, so open a new task to be safe).

- **Installed from a local clone**: new Claude sessions read the clone directly, so after `git -C <clone> pull
  --ff-only` just open a new session. The user-scope record's version label in `claude plugin list` does not follow,
  and doctor warns about it; refresh it with `claude plugin marketplace update agent-relay-marketplace` and
  `claude plugin update --scope user agent-relay@agent-relay-marketplace` (measured on this Mac when upgrading to
  0.9.2); these two steps only change the label. For Codex run `codex plugin add agent-relay@agent-relay-marketplace`
  again.
- **Installed from GitHub**: first `claude plugin marketplace update agent-relay-marketplace`, then
  `claude plugin update --scope user agent-relay@agent-relay-marketplace`. Without `--scope` this updates only the
  "current folder" project-level entry, not the user-level install (measured on this Mac). Then open a new session.
- **Codex**: after updating the plugin, quit the ChatGPT app completely with ⌘Q and reopen it so open threads pick up
  the new version.

The `claude-plugin` item of `python3 -B <plugin dir>/hooks/native_collaboration_runtime.py doctor` checks the version
of the copy a new session will load (it reads that copy's `plugin.json`, not the version `claude plugin list` shows)
and gives the command to run when they differ. A version in `claude plugin list` that disagrees with doctor
is a stale label on that record, not the copy that loads; doctor warns and lists those records with the cleanup
commands (`claude plugin uninstall --scope local` per folder, or an update of the record) for you to run one by one;
doctor itself changes nothing. Records whose folder is gone are not warned about or listed: they are counted, with a
note that they can stay or be removed as it describes; a project scope record gets a note, not a command, because
changing it changes that repository's committed `.claude/settings.json`. When the plugin carries new bridge runtime
code (a bridge change in tests or docs only does not count), also upgrade the runtime as in the next section; the top
of each CHANGELOG entry says whether it is needed.

### Upgrading the runtime

**Update the plugin first, then the runtime**: a new bridge may move the mailbox to a new schema (0.7.0 moves it to 6),
which older plugins' hooks cannot read, so retiring and delegation would stop. Update the plugin on both hosts first
(open new sessions; quit and reopen the ChatGPT app), then upgrade as below.

When a plugin update brings new bridge runtime code, `status` reports `bridge.current: false` (a bridge change in tests
or docs only does not count). The agent asks you first, and after you close every session that uses the mailbox it
runs
`python3 -B <plugin dir>/hooks/native_collaboration_runtime.py upgrade --confirm`: it backs the mailbox up to
`~/.agent-relay/backups/<time>/`, builds the new version beside the old one, moves `mailbox/` and `data/` across,
swaps in whole, counts as done only after the checks pass, and swaps back on failure. The old directory
`runtime.previous-<time>` is kept; delete it yourself once you are sure; host attachment does not change. The new
bridge upgrades the mailbox to schema 7 (from any earlier schema in one step, backed up first): the old runtime can
still open it, but older agent-relay plugins cannot read the new schema (0.7.x reads up to 6), so roll back the plugin together with the runtime, or
restore the mailbox from the backup (messages received after that are lost).

Stop the bridges in one of two ways before upgrading, then check in Terminal that
`pgrep -fl "agent-relay/runtime/dist/server.js"` prints nothing:

- **Quit the apps**: close every Claude Code session and quit the ChatGPT app with ⌘Q (it starts Codex's bridge).
  Reopen them after the upgrade.
- **End only the bridge processes**: `pkill -TERM -f "[a]gent-relay/runtime/dist/server.js"` (the brackets keep it from
  matching the shell that runs it). After the upgrade, reopen the Claude Code sessions; quit the ChatGPT app completely
  with ⌘Q and reopen it, otherwise open Codex threads keep reporting "Transport closed".

On success, the output's `next` reminds you to reopen the ChatGPT app. After that, doctor's `codex-restart` item
compares the ChatGPT app's start time with the latest upgrade (the newest `runtime.previous-<time>`): it warns while
the app is still the one opened before the upgrade and turns ok after reopening. `codex` sessions running in a terminal
also need to be restarted after the upgrade; doctor cannot see those.

- **Rollback**: likewise close all sessions and run
  `python3 -B <plugin dir>/hooks/native_collaboration_runtime.py rollback --confirm`, which returns to the newest
  `runtime.previous-<time>` taking the mailbox and data along; the mailbox is backed up first and the current version
  is kept as `runtime.rolled-back-<time>`.
- **Interrupted**: when an upgrade, reinstall or rollback stops halfway (process killed, power loss),
  `~/.agent-relay/runtime-swap.json` records it, `status` reports `interrupted`, doctor fails and other commands refuse.
  Close all sessions and run `python3 -B <plugin dir>/hooks/native_collaboration_runtime.py recover --confirm`: it
  always returns to the runtime from before the swap (never completes it forward), keeping the part that was not
  swapped in as `.runtime-<kind>-failed-<time>`. Then you can upgrade again.
- `runtime.previous-*`, `runtime.rolled-back-*` and `.runtime-*-failed-*` are never deleted automatically; delete them
  yourself once you are sure.

After an upgrade each session registers its original name once again (recording its session).

## Uninstalling

For a complete uninstall follow this order (the `collaboration-ops` skill asks you at each step); message history is
kept by default:

1. Close every session that uses the mailbox (for Claude this means **every** Claude Code session, see step 3).
2. `python3 -B <plugin dir>/hooks/native_collaboration_runtime.py doctor`: see which hosts are attached.
3. Remove the host configuration:
   `python3 -B <plugin dir>/hooks/native_collaboration_adapters.py uninstall-codex --confirm-uninstall` and
   `uninstall-claude --confirm-uninstall`.
   - Before every write to host configuration (install and uninstall alike), the files to change are copied to
     `~/.agent-relay/backups/<UTC time>/host-config/` and the path is printed. These copies may contain credentials
     such as MCP API keys; the directory and files are readable only by you (0700 / 0600); delete them when done.
   - Codex: also removes the tool approval subtables Codex writes when you choose "always allow" (a single
     `approval_mode` line each), and recognizes a changed node version. Any other difference is pointed out line by
     line (line numbers and key names only, never values) and left to you.
   - Claude: removes the MCP entry; if this machine was installed with 0.4.0 or earlier, it also removes the 7 deny
     rules written then (since 0.5.0 the server offers only the ten mailbox tools and install no longer writes those
     rules); other settings are untouched. While any Claude Code session is open (or this runtime's bridge still runs),
     it removes only the entry and keeps the 7 rules: an open old session refilters its cached tool list against the
     new settings, and removing the rules would expose the deleted worker tools. So run this step **in a terminal,
     after closing every Claude Code session**; run from any Claude session (including by the agent) it keeps the rules
     and prints the terminal command to copy.
4. Remove the runtime: `python3 -B <plugin dir>/hooks/native_collaboration_runtime.py uninstall --confirm`. Only the
   build output is deleted; `mailbox/` (message history and backups) and `data/` stay, and a later `install` rebuilds
   around them.
5. Uninstall the plugin: `claude plugin uninstall agent-relay@agent-relay-marketplace`;
   `codex plugin remove agent-relay@agent-relay-marketplace`.
6. Run `doctor` once more (before uninstalling the plugin also works): hosts not attached, runtime uninstalled, and the
   path of the history.

When you no longer need the message history, deleting `~/.agent-relay/` is up to you. A `codex-gate.off` left in the
mailbox directory by an old version is no longer used and can be deleted (agent-relay will not delete it for you).

## Advanced settings

### Finding the plugin directory

The commands above are written as `<plugin dir>/hooks/…`. The plugin directory is the copy the host actually loaded
(installed from GitHub: in the host's plugin cache; installed from a local clone: `plugins/agent-relay` in the clone).
To find it:

```bash
claude plugin list --json | python3 -c 'import json,sys; ps=[p for p in json.load(sys.stdin) if p.get("id","").startswith("agent-relay@") and p.get("enabled")]; p=next((p for p in ps if p.get("scope")=="user"), ps[0] if ps else {}); print(p.get("readFromFolder") or p.get("installPath") or "")'
codex plugin list --json | python3 -c 'import json,sys; print(next((p["source"]["path"] for p in json.load(sys.stdin).get("installed",[]) if p.get("name")=="agent-relay" and p.get("enabled") and (p.get("source") or {}).get("path")), ""))'
```

The first is for Claude Code, the second for Codex; with both installed, either printed directory will do. When you
let the agent do it you can skip this: the skills find the plugin directory themselves.

### Using another state directory

The runtime, mailbox, delegation records and migration backups live in `~/.agent-relay/` by default. Setting the
environment variable `AGENT_RELAY_HOME` (an absolute path; a relative path is an error) moves all of them, and every
agent-relay command uses that directory; an explicit `--root` or `--state-root` on the command line still wins. Note:
attaching a host writes the absolute path resolved at that time into the host configuration, so changing the variable
later does **not** move hosts already attached; install the runtime under the new directory and attach the hosts again.

## Relationship with Spec Guard

The two plugins are independent; either can be installed alone. When both are installed, Spec Guard reads
[`interface.json`](plugins/agent-relay/interface.json) in this plugin's root (interface 2.10; Spec Guard accepts
`>=1.0,<3.0` since 0.56.0) to decide whether agent-relay is available, and uses collaboration only through
agent-relay's skill names; without it, Spec Guard's workflows run as usual and only the steps that need collaboration
suggest installing it.

### Migrating from Spec Guard's collaboration feature

If you used Spec Guard's built-in collaboration, the old data is in `~/.spec-guard/native-collaboration/` and
`~/.spec-guard/session-delegation/`. Let the agent follow the migration steps of `collaboration-ops`, or run:

```bash
python3 -B <plugin dir>/hooks/state_migration.py detect
python3 -B <plugin dir>/hooks/state_migration.py migrate --confirm
```

- `detect` is read-only: it lists how much old data there is and what blocks the migration: unfinished delegations, old
  mailbox servers still running (close or restart those sessions first), the agent-relay runtime not yet installed. A
  stuck delegation that never started can be let through with `--acknowledge-stale <id>` once you are sure it is no
  longer needed.
- `migrate` first backs the old data up to `~/.agent-relay/backups/<time>/`, then copies it into agent-relay and checks
  every table's count; it only migrates into a fresh agent-relay (empty mailbox) and never merges two mailboxes. One
  migration at a time; it also refuses while agent-relay's own mailbox server runs (close all sessions first).
  Everything is prepared beside the target and swapped in whole after the counts match; any failure puts back the state
  before the migration, and the part that was not swapped in stays in `~/.agent-relay/.state-migration-failed-<time>`
  for inspection.
- When a migration is interrupted (process killed, power loss), `detect` reports `interrupted` and `migrate` refuses;
  close all sessions and run `state_migration.py recover --confirm`, which always returns to the state before the
  migration; then you can migrate again. None of these directories is deleted automatically.
- After a successful migration, the replaced target directory (including the mailbox from before the migration) stays
  in `~/.agent-relay/.state-migration-<time>-<random>/previous-*`, path given as `previous` in the result; delete the
  whole directory yourself once you are sure the migration is correct.
- Old directories, host configuration and permission files are never touched; after migrating, attach the new host
  entries as prompted, remove the old ones with Spec Guard's own uninstall, and change project permission rules to
  `mcp__agent-relay__bridge_*` by hand. Delete the old directories yourself once you are sure.

## Glossary

| Term | Meaning |
|---|---|
| Host | The application a session runs in: Claude Code (CLI or desktop app) or Codex (the ChatGPT app or CLI) |
| Mailbox | A private local SQLite mailbox that stores every message sent through agent-relay, in `~/.agent-relay/runtime/mailbox/` |
| Bridge | The MCP server (`agent-relay`) in each session that connects to the mailbox, offers the 10 `bridge_*` tools and handles delivery and wake |
| Runtime | The built bridge program and mailbox under `~/.agent-relay/runtime/`; managed by `install`/`upgrade` |
| Identity | The name a session registered in the mailbox; it belongs to that session and can be retired when done |
| Wake binding | Binding an identity to the current session (`wake`) so the bridge wakes it when a message arrives; off by default |
| Script identity | An identity the user registers in a terminal for scripts and launchd; it can send but not acknowledge |
| Delivery state | How far a direct message got: `queued`, `sending`, `accepted`, `failed`, `unknown`, `expired` |
| `held` | Two meanings: a delegation missing a prerequisite and not started (`held/<reason>`); or Claude Code holding the pings sent to a session |
| `expectsReply` | The sender marks a message as a request; the recipient answers it with `replyTo` when done, an ack alone does not count |
| `not-loaded` | The ChatGPT app has not opened that Codex task since it started |
| Delegation | One side opens a new limited session on the other host to do work; the result comes back through the mailbox |

## Documentation

- [Interface document](docs/collaboration-interface.md): tools, messages, states, delivery semantics, identity,
  authorization, delegation and hardening targets.
- [Notices and delivery details](docs/notifications.en.md): notice channel, click actions, preview switches, the
  per-recipient cap, retry keys and reply rules.
- [Changelog](CHANGELOG.md): version changes and upgrade steps (in Chinese).
- [Security](SECURITY.md): what is protected, trust boundaries and how to report a security problem (in Chinese).
- [Background wake](plugins/agent-relay/bridge/docs/BACKGROUND-WAKE.md): how wake works and why Claude pings expire.
- [Runtime notes](plugins/agent-relay/references/collaboration-runtime.md),
  [collaboration protocol](plugins/agent-relay/references/collaboration-protocol.md).
- Developing, running the tests and releasing: see [CONTRIBUTING.md](CONTRIBUTING.md) (in Chinese).

## License and credits

agent-relay is released under the [MIT license](LICENSE).
The mailbox runtime is based on Tesla Major's
[claude-codex-mcp-bridge](https://github.com/WebisityStudio/claude-codex-mcp-bridge) (MIT); a copy pinned at commit
`8f12c88` lives in [`plugins/agent-relay/bridge/`](plugins/agent-relay/bridge/) and is maintained by agent-relay;
origin, license text and change log are in [`UPSTREAM.md`](plugins/agent-relay/bridge/UPSTREAM.md).
