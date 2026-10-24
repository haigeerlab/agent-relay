# agent-relay

[简体中文](README.md) | English

Lets Claude Code and Codex sessions on **the same Mac** pass messages to each other, find each other by name, and,
within a limited authorization you give, create and continue review or development sessions. No copying and pasting
between sessions, and no workflow plugin required.

agent-relay started as an optional collaboration feature of [Spec Guard](https://github.com/haigeerlab/spec-guard-plugin)
and is now a standalone plugin: a project that only needs its sessions to talk to each other (a design project, for
example) needs nothing else.

> Status: 0.9.2 (interface 2.8, needs Spec Guard 0.56.0 or later). Changes, upgrade steps and known issues are in
> [CHANGELOG.md](CHANGELOG.md) (written in Chinese); the goal of each item is in the "hardening target" column of
> [docs/collaboration-interface.md](docs/collaboration-interface.md).

## What it does

| Capability | Description | Entry point |
|---|---|---|
| Collaboration mailbox | Sessions on the same Mac send and reply to messages; across hosts (Claude Code ↔ Codex) they go through a private local bridge | `collab` skill; Claude Code also has `/agent-relay:collaboration` |
| Session routing | Reach another session by its name; on the same host the host's own messaging is preferred (Claude Code `SendMessage`, Codex App threads), the mailbox only across hosts | `session-routing` skill |
| Cross-host session delegation | One sentence lets the current Claude Code session create a Codex review session, or Codex create a Claude Code development session (only these two directions, no same-host delegation); by default a limited authorization for one task in one new session; a read-only review can be limited with `--scope` (Claude Code sessions hard-block reads outside it); a delegated session can be reached by the name you gave it; stuck delegation records can be previewed and then cleaned with `prune`; when Codex creates a Claude Code session it can optionally "load the user environment" (`--user-environment`, off by default) so it brings your settings, plugins and skills. When the delegate plugin is installed in Claude Code, "hand it to Codex" goes to delegate and this is only the fallback | `session-delegation` skill |
| Runtime management | Inspect and, with your consent, install the local mailbox runtime, attach or detach host configuration, retire identities that ended | `collaboration-ops` skill |

## Requirements

- macOS; Node.js 22.5 or later (the mailbox runtime uses the built-in `node:sqlite`, available from 22.5.0); Python 3.9
  to 3.14 (macOS's own `/usr/bin/python3` 3.9 works; the full test suite has run on 3.9, 3.10 and 3.14).
- The delegation controller, `doctor`, the runtime's `install`/`upgrade`, identity retirement and the host adapters
  (`install-claude`/`install-codex` and the printed configuration) use the node pinned in the host entries (order:
  `--node` → Claude entry → Codex entry → PATH), not the current shell's PATH; npm runs on that node during install,
  and `--npm` defaults to the npm beside it. A selected node below 22.5.0 is refused (`node-too-old`) before any host
  is touched or any build starts.
- Claude Code and/or Codex (App or CLI).

## Installation

Claude Code:

```bash
claude plugin marketplace add haigeerlab/agent-relay
claude plugin install agent-relay@agent-relay-marketplace
```

Codex (pinned to the released version):

```bash
codex plugin marketplace add haigeerlab/agent-relay --ref v0.9.2
codex plugin add agent-relay@agent-relay-marketplace
```

For development you can replace `haigeerlab/agent-relay` above with the path of a local clone.

Installing the plugin only loads its skills and command. It does **not** create the runtime or change host
configuration. On first use the agent checks read-only, tells you which steps are needed, and waits for your consent
at each one:

1. Install the private runtime: from the bridge copy shipped in the plugin, verified against its hashes, it builds the
   runtime and a private mailbox in `~/.agent-relay/runtime/` (readable and writable only by you). No git is needed;
   `npm` dependencies are still installed from the npm registry by the lockfile, so this step needs network.
2. Attach the hosts: register the user-level MCP server `agent-relay` for Claude Code, or append
   `[mcp_servers.agent_relay]` to the Codex configuration. Sessions that are already open need a restart to see it.

### Finding the plugin directory

The commands below are written as `<plugin dir>/hooks/…`. The plugin directory is the copy the host actually loaded
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

## Before you start: checklist

Go through it once; after that all that is left is "say one sentence to a session". Details are in the sections
below; this only lists what to do.

**Once**

1. Install the plugin on both hosts (see "Installation").
2. Ask the agent to "check the agent-relay status" and follow the steps it lists to set up the runtime and attach the
   hosts; each step waits for your consent. Then restart the sessions that were already open.
3. Codex: attaching writes `approval_mode = "approve"` for the 10 mailbox tools and lists the entries it wrote to
   `~/.codex/config.toml`; nothing else to configure.
4. Claude Code: the 10 mailbox tools ask for confirmation on every call by default. To stop that, run
   `python3 -B <plugin dir>/hooks/native_collaboration_adapters.py claude-allow-rules` and add the 10 rules it prints to
   `permissions.allow` in `~/.claude/settings.json`. Whether to add them is your choice; agent-relay never edits that
   file.
5. Run `python3 -B <plugin dir>/hooks/native_collaboration_runtime.py doctor`; every item should be ok (a `warn` names
   its next step).

**Once per project**

- Claude Code: trust the project. The trust dialog preselects "No, exit"; pressing Enter quits, so select "Yes" first.
- Codex: when adding the project in the App, choose to trust the folder.

**One sentence per session**

- Tell the session "join local collaboration and allow wake, use the name X" (in Chinese: "加入本机联调并允许唤醒，名字用 X";
  any language works). Without "allow wake", the session is not woken when another session sends it a message.
- Any permission mode can join, including Claude's auto mode; the exception is Bypass permissions, which holds incoming
  pings until they expire (see "Authorization and safety").
- When the name is held by an old session that has stopped, choosing another name is simplest; only if you insist on
  the original name do you need to agree to a takeover.

**Additionally for delegation** (one side opens a new limited session to do work; only Claude Code → Codex and Codex →
Claude Code)

- The session that starts the delegation joins and allows wake first, so the result comes back to it automatically.
- When the target is Claude Code, the target project's `.claude/settings.json` or `.claude/settings.local.json` needs an
  allow for the 10 mailbox tools; the user-level `~/.claude/settings.json` alone does not count, unless you use the next
  item.
- To let the delegated Claude Code session bring your own settings, plugins and skills, say "load my user environment"
  when creating it and add `Skill` to the allow list; if something is missing you see `held` and the rule to add before
  anything starts, rather than a half-working session.

**What you do not need to set up in advance**

The permissions the other session needs for its work (reading files, running commands) are that session's own
settings: it asks you when it needs them. When a wake-bound Claude Code session is stuck on an approval prompt, this
Mac shows a notice and the session directory marks it "waiting for approval"; a Codex session stuck on an approval
still shows as running in the directory, so check the ChatGPT app. agent-relay never changes any session's permissions.

**After an upgrade**

- After updating the plugin, **open a new session** to use it; sessions already open, reopened after restarting the
  app, or resumed still use the old copy (see "Updating the plugin").
- When a release adds parameters to the mailbox tools (such as `expectsReply` and `awaitingReply` in 0.7.0), a session
  that is already open keeps the old parameter definitions even after the bridge restarts and the tools are reloaded,
  and a new parameter is refused (`expected boolean`). To use the new parameters, open a new Claude Code session or a
  new Codex task. (Measured for Claude Code; whether an old Codex task gets the new parameters after the app is
  reopened was not measured, so open a new task to be safe.)
- Claude Code installed from GitHub: `claude plugin update` needs `--scope user`; without it only the current folder's
  project-level entry is updated.
- Codex: after updating the plugin, quit the ChatGPT app completely with ⌘Q and reopen it so open threads pick up the
  new version.
- Versions that change the bridge also need a runtime upgrade (see "Upgrading the runtime"); the top of each CHANGELOG
  entry says whether it is needed.

## How to use it

Just say it in natural language; no tool names or internal IDs to remember:

- "Join local collaboration", "show collaboration messages", "which sessions are there" → join the mailbox, read the
  inbox and the directory.
- "Tell the session of the design project in Codex: the home page draft is at `designs/home.fig`, please confirm" →
  finds the session by name and sends the message; when several sessions share the name you get short ids to choose
  from.
- "Reply to that session" → replies to the most recent message.
- "Create a Codex review of these changes" → creates a read-only review session; the result comes back to the current
  session.
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
- The first time in Claude Code, every mailbox tool asks once (`mailbox-polish`): to allow them all at once, run
  `python3 -B <plugin dir>/hooks/native_collaboration_adapters.py claude-allow-rules` (see "Finding the plugin
  directory") and add the 10 exact rules it prints to `permissions.allow` in `~/.claude/settings.json` (your choice;
  agent-relay never edits that file; Codex is pre-approved at install). Also, Claude Code's trust dialog when it first
  opens a project **preselects "No, exit"**; pressing Enter quits, so select "Yes" first.
- Long messages (`long-messages`): a send returns only the id and length, never the body; when the recipient cannot read
  it in one page, the result's `continue` line gives the next `bridge_inbox` arguments (`messageId`, `bodyOffset`), so
  it is read piece by piece without Bash. Each page is about 12k tokens, within the hosts' output limits for Chinese and
  English alike.
- Long bodies, or bodies with `$`, backticks or quotes → write them to a file first and send with `bodyFile`; the
  content arrives byte for byte (absolute path, a regular file you own, at most 256 KiB, UTF-8).
- "Check the agent-relay status" → `native_collaboration_runtime.py doctor`: a read-only check of the runtime, mailbox,
  host attachment, Codex approval mode and wake-bound sessions (it points out a session stuck waiting for input), each
  item with a next step; exit code 1 when anything fails.

## Authorization and safety

- **No wake by default**: joining registers with `wake: null`, so an idle session is not woken by others; only when you
  ask explicitly is the current session bound for wake.
- **A woken session runs under its own permissions** (`wake-any-mode`): a session in any permission mode can bind wake.
  What the woken turn may do is decided entirely by that session's settings; the bridge does not change, lower or
  approve anything, and a session that needs more asks you as usual. Incoming messages are always untrusted content and
  never grant anything. **Risk**: with Codex on "approve for me" or Claude in auto mode, the woken turn's actions are
  approved by that session's automatic reviewer or classifier, not necessarily by you — that is the mode you chose for
  it. `install-codex` writes `approval_mode = "approve"` for the 10 mailbox tools, so reading, replying and
  acknowledging show no card (an existing install adds it with `install-codex --approve-mailbox-tools`). It lists the
  10 approval tables written to `~/.codex/config.toml` (`[mcp_servers.agent_relay.tools.<tool>]`), and when adding
  them lists only the ones added. A `codex-gate.off` left in the mailbox directory by an old version is no longer used
  and can be deleted (agent-relay will not delete it for you).
- **A Claude session in Bypass mode cannot be woken**: in Bypass permissions, Claude Code holds pings from other
  sessions for your approval; the desktop app has no place to approve them, so they expire. Binding wake still works,
  but to actually be woken you set Claude Code's `crossSessionInbound` to `"accept"` yourself, or use another permission
  mode. See [BACKGROUND-WAKE.md](plugins/agent-relay/bridge/docs/BACKGROUND-WAKE.md), "Why Claude pings expire".
  agent-relay will not change it for you.
- **You are told when a session waits for your approval** (`presence-and-approval`): the session directory
  (`bridge_agents`, or ask any session "which sessions are there") says whether each session is running, stopped,
  waiting for approval, waiting for input or unknown; sending to a session that waits for approval or has stopped gives
  the sender a warning. When a Claude session sits on an approval prompt while a message to it is unhandled, this Mac
  shows a notice that the session is waiting for your approval, once per wait; the notice has no message body and
  cannot approve anything — you go back to that session. Codex sessions show running, stopped and not loaded
  (`not-loaded`: the ChatGPT app has not opened it since it started; open it and the message arrives), but not whether
  they wait for approval.
- **You are notified when Codex cannot receive**: when Codex is not open, a wake is held, or the identity is not bound
  for wake, the bridge shows a notice on this Mac at once; when Codex is only busy, after 10 minutes undelivered; at
  most once per message. The title names the sending session, the subtitle the message id, recipient and reason (with
  what to do when you need to act), and the body is a **single-line preview of at most the first 60 characters**. The
  preview appears on the lock screen and shared screens (macOS's "Show previews" setting can limit that); to hide the
  body, put a `notify-preview.off` file in the mailbox directory (`~/.agent-relay/runtime/mailbox/`), which falls back
  to ids only; to turn notices off entirely, put `notify.off` there.
- **You are notified when a Claude session is not running**: the Claude desktop app stops the process of an idle
  session, and the bridge can only deliver to a running one. When a message to such a session has not gone in for five
  minutes, this Mac shows a notice naming the session (its mailbox name), how many messages are waiting and when the
  first was sent; once per offline spell, and opening the session delivers them. No message body and no click action.
  The sender sees `pendingReason: offline` in `bridge_outbox`. `notify.off` turns this off too.
  **Channel**: with Homebrew's terminal-notifier installed (only `/opt/homebrew/bin` and `/usr/local/bin`, not looked up
  in PATH) it is used, otherwise `osascript`. `osascript` notices are filed under Script Editor, which never asks for
  notification permission, so on most Macs they are **silently dropped** with no switch in System Settings; to see
  banners, `brew install terminal-notifier` (your choice) and allow it on its first notice. The bridge cannot see
  whether macOS showed a notice, so wake details and sender warnings say only "attempted". doctor's `notifications`
  check judges whether the actual channel looks allowed, and `doctor --test-notification` shows a test notice through
  the same channel for you to confirm.
- **Notices say where the session is, and a click takes you there**: the subtitle of a "waiting for your approval"
  notice gives the session name, project directory name and place (Claude desktop app, the terminal's tty, a background
  session and the `claude attach <id>` that opens it); a Codex notice says "Codex app" when the app confirms it holds
  that thread. With terminal-notifier, clicking the notice brings the application forward, and Terminal and iTerm also
  switch to that tab; background sessions, sessions inside tmux/ssh and notices whose place is unknown have no click
  action. **A click only switches windows; it approves nothing and types nothing into the session.** The first click on
  a terminal session's notice makes macOS ask once, on behalf of terminal-notifier, for "Automation" permission (to
  control Terminal or iTerm); without it the terminal app still comes forward but the tab is not selected, and you can
  change it later in System Settings → Privacy & Security → Automation. With previews off (`notify-preview.off`) the
  text gives only the kind of place, and clicks still work.
  The place you can always see is the **waiting list**: ask any session "which messages are waiting for Codex", or run
  doctor and read `codex-waiting` (counts, senders and ids only, no bodies).
- **The sender is warned when the recipient cannot be pinged**: when the recipient is neither bound for wake nor known
  to be on a host (for example Codex registered with `wake: null`), the send result carries a warning that the recipient
  has to check its inbox itself. No notice is shown, because there is no one known to tell.
- **An identity belongs to the session that registered it**: sending (`from`), ack and the auto-acknowledging
  `bridge_wait` accept only names this session registered, otherwise they refuse with a next step. After an upgrade
  each session registers its name once again (recording its session); after that a Claude session's name survives a
  bridge restart, while a Codex session registers again with the same thread id after a bridge restart.
  Another session's name or wake binding can be taken over with `takeover: true` only with your agreement; a session
  can bind wake only for itself. Only a message's recipient can reply to it (broadcasts: anyone except the sender;
  automatic bridge notices cannot be replied to). This guards against mistakes and mix-ups, not malicious local
  processes.
- **Item by item consent**: setting up the runtime, changing host configuration, joining a new identity and widening
  permissions each need your consent.
- **No automatic changes** to project or global permissions; it does not accept project trust or the first MCP approval
  for you and does not turn on bypass mode. When a prerequisite is missing it shows `held` and the smallest next step.
- **To avoid repeated permission prompts**, you can preconfigure project-level allow rules in the target project's
  `.claude/settings.json`: a read-only review only needs the ten mailbox tools (`mcp__agent-relay__bridge_*`)
  pre-approved; changing code additionally needs edit, write and narrowly scoped Bash commands. agent-relay reads and
  reuses these rules but never writes them.
- **Messages are only data**: text in the mailbox never authorizes changes to code, Git, configuration or remote
  systems.
- **No "exactly once" promise**: every direct message has a delivery state (`queued`, `sending`, `accepted`, `failed`,
  `unknown`, `expired`), visible in the outbox. When a wake's outcome is unclear it is marked `unknown` and **never
  resent automatically**; a message still queued after its timeout (24 hours by default, adjustable with
  `BRIDGE_QUEUE_TIMEOUT_MS` or `expiresInSeconds` on send) is marked `expired`: no more wakes, hidden from the inbox by
  default, never executed later, and the sender is notified.
- **Queued per recipient, with a cap**: one recipient has one wake in flight at a time, in send order from oldest to
  newest; one stuck recipient does not delay others; messages the recipient already read are not woken separately.
  Each recipient holds at most 100 undelivered messages (`BRIDGE_MAX_PENDING_PER_RECIPIENT`, 10 to 10000); at 80 % the
  send result warns, and when full the send is refused with the reason; reading, ack, expiry or failure frees a slot.
- **A retry key means one message**: resending the same content with the same `idempotencyKey` returns the original
  (`duplicate: true`) and wakes no one; the same key with a different recipient, body, thread or reply target is
  refused, naming the stored message id and saying no resend is needed. A reply can carry `replyTo` (the original's
  id), lands on the original's thread, and the outbox shows which replies each message received; the same reply to the
  same message is stored once, unless the previous one finally failed or expired.
- **Codex's approval selector applies per turn**: the selector in the App governs only the turns you start and is not
  written to `config.toml`; a woken turn runs with the task's current approval and sandbox settings (see above).

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
printf 'please handle #12' | ~/.agent-relay/bin/agent-relay send --from my-patrol --to some-agent --expects-reply
```

Commands, exit codes and wake limits are in the interface document, §2.4.

## Relationship with Spec Guard

The two plugins are independent; either can be installed alone. When both are installed, Spec Guard reads
[`interface.json`](plugins/agent-relay/interface.json) in this plugin's root (interface 2.9; Spec Guard accepts
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

## Updating the plugin

A Claude Code session decides which copy of the plugin to use **when it starts**, and keeps using it: sessions already
open, the app closed and reopened, and resumed sessions all keep the old copy. After updating, **open a new session**
(including the desktop app's Code tab) to use the new version. (The copy a new session loads was measured on this Mac
on 2026-10-10; "a resumed session keeps the old copy" is one case observed by the coordinator.) The mailbox tool
parameter definitions behave the same way: an open Claude Code session does not get new parameters by reconnecting
MCP (measured on this Mac after the 0.7.0 upgrade).

- **Installed from a local clone**: new Claude sessions read the clone directly, so after `git -C <clone> pull
  --ff-only` just open a new session. The user-scope record's version label in `claude plugin list` does not follow,
  and doctor warns about it; refresh it with `claude plugin marketplace update agent-relay-marketplace` and
  `claude plugin update --scope user agent-relay@agent-relay-marketplace` (measured on this Mac when upgrading to
  0.9.2); these two steps only change the label. For Codex run `codex plugin add agent-relay@agent-relay-marketplace`
  again.
- **Installed from GitHub**: first `claude plugin marketplace update agent-relay-marketplace`, then
  `claude plugin update --scope user agent-relay@agent-relay-marketplace`. Without `--scope` this updates only the
  "current folder" project-level entry, not the user-level install (measured on this Mac). Then open a new session.

The `claude-plugin` item of `python3 -B <plugin dir>/hooks/native_collaboration_runtime.py doctor` checks the version
of the copy a new session will load (it reads that copy's `plugin.json`, not the version `claude plugin list` shows)
and gives the command to run when they differ. A version in `claude plugin list` that disagrees with doctor
is a stale label on that record, not the copy that loads; doctor warns and lists those records with the cleanup
commands (`claude plugin uninstall --scope local` per folder, or an update of the record) for you to run one by one;
doctor itself changes nothing. Records whose folder is gone are not warned about or listed: they are counted, with a
note that they can stay or be removed as it describes; a project scope record gets a note, not a command, because
changing it changes that repository's committed `.claude/settings.json`. When the plugin carries new bridge runtime code (a bridge change in tests or docs only
does not count), also upgrade the runtime as in the next section.

## Upgrading the runtime

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

When you no longer need the message history, deleting `~/.agent-relay/` is up to you.

## Documentation

- [Interface document](docs/collaboration-interface.md): tools, messages, states, delivery semantics, identity,
  authorization, delegation and hardening targets.
- [Acceptance checklist](docs/acceptance/checklist.md): real-host acceptance steps.
- [Changelog](CHANGELOG.md): version changes and known issues (in Chinese).
- [Releasing](RELEASING.md): the maintainer's steps and checks for a new version (in Chinese).
- [Security](SECURITY.md): what is protected, trust boundaries and how to report a security problem (in Chinese).
- [Background wake](plugins/agent-relay/bridge/docs/BACKGROUND-WAKE.md): how wake works and why Claude pings expire.
- [Runtime notes](plugins/agent-relay/references/collaboration-runtime.md),
  [collaboration protocol](plugins/agent-relay/references/collaboration-protocol.md).

## Development and CI

Local validation: `bash scripts/validate.sh` (run `npm ci` in `plugins/agent-relay/bridge` first, otherwise the bridge
part shows skip). Every PR and every commit pushed to `main` runs the same validation on GitHub Actions `macos-15`,
across Python 3.9 (shipped with Apple's command line tools) / 3.14 × Node 22 / 24; the log has doctor's `toolchain`
line naming the Python and Node actually used. To make it a required check for `main`: repository Settings → Branches
(or Rules → Rulesets) → for `main` tick "Require status checks to pass" and select the four `Python … / Node …`
checks. Whether to do so is the maintainer's decision.

Run only when needed (`ci-on-demand`): a PR (or a commit pushed to `main`) that only changes files under `CLAUDE.md`,
`AGENTS.md`, `spec/`, `tasks/` or `.agent/` passes the four checks after printing the reason, without running tests;
any file outside these runs the full matrix. The list is defined in [`scripts/ci_scope.py`](scripts/ci_scope.py), and
`hooks/test_ci_exempt_guard.py` ensures the code under test reads none of these paths. Every Monday at 03:00 UTC a full
run on `main` catches problems from Python or Node upgrades in the runners; to run it all at any time, use "Run
workflow" for CI on the Actions page.

## License and credits

agent-relay is released under the [MIT license](LICENSE).
The mailbox runtime is based on Tesla Major's
[claude-codex-mcp-bridge](https://github.com/WebisityStudio/claude-codex-mcp-bridge) (MIT); a copy pinned at commit
`8f12c88` lives in [`plugins/agent-relay/bridge/`](plugins/agent-relay/bridge/) and is maintained by agent-relay;
origin, license text and change log are in [`UPSTREAM.md`](plugins/agent-relay/bridge/UPSTREAM.md).
