# Spec: paused-session-link

<!-- spec-guard: review approved 94b3c1101801 -->

## Objective

Local ledger item F5GR1D3, from ecosystem-lead's request (mailbox #22999, 2026-11-25): the user finds sessions
"disconnected" far too often — a Claude session that answered half an hour ago no longer wakes, and only opening it or
typing into it brings it back. ecosystem-lead traced it to the Claude desktop app, not agent-relay: under macOS memory
pressure its `[CliGovernor]` pauses idle sessions (`Pausing session … (governor_evict)`, 628 times since 11-18 against 4
idle timeouts, at most 6 live sessions). Pausing is the host's behaviour and stays as it is.

What agent-relay can do is make a paused recipient obvious and quick to fix: say plainly to the sender and the user that
the session must be opened, name it so the user can find it, let the notification open it with one click, and tell a
Claude sender how it may wake it by hand when the user asks. Scope set by the user in the owner session: 「做 A+B，C 手动
叫醒」 (2026-11-25), 「跳到了那个会话，假设都同意，C 保留说明」 (2026-11-26). ecosystem-lead gets this Spec before review
(interface change).

Readers: the user; the owner session (review, release, acceptance); ecosystem-lead (interface 2.12).

## What exists today (main b5a6eb6, v0.9.6, interface 2.11, schema 7)

- Send time (`addressing.ts`): a Claude recipient whose presence is `stopped` gets the warning `"<agent>"'s Claude session
  is not running. The message will wait in its inbox until that conversation reads it.`
- Outbox (`claude-wake.ts` `CLAUDE_NOT_RUNNING`, D193): a pending wake shows `pendingReason: "offline"` and
  `Claude session is not running (the Claude app may have stopped it while idle); the message waits and is delivered once
  that session is opened`.
- Notification (`wake-dispatcher.ts` `noticeClaudeOffline`, `notify.ts`, D193/D194): once per offline spell, five minutes
  after the first waiting message, title `agent-relay · <agent> is offline`, body from `noticeText`, **no click** ("the
  place is not known once the process is gone").
- Expiry (`notices.ts` `CLAUDE_OFFLINE_EXPLANATION`, D215): after the one-hour window the sender gets a bridge notice
  ending "ask the user to open it".
- `bridge_agents` already shows `waiting` and presence `stopped` (ecosystem-lead's item 3 needs nothing new).
- Clicks (`location.ts` `clickArgs`, D188/D190): terminal-notifier gets `-activate <bundle>` or `-execute <script>`; the
  osascript fallback has no click.
- `bridge_register` takes `agent`, `wake`, `capabilities`, `takeover`, `reactivate`, `host` (Codex only). The bridge
  knows a Claude session by its CLI session id, not by the desktop app's `local_…` id, so it cannot point at the session.
- Mailbox data, last 7 days (read-only): Claude recipients went `offline` and were delivered later 147 times, and
  expired offline 62 times.

Measured on this Mac (2026-11-25/26), the facts this Spec relies on:
- The desktop app's own tool `get_session("self")` (Claude Code in the desktop app, `ccd_session_mgmt`) returns the
  session's `title` and `link` `claude://claude.ai/epitaxy/local_<uuid>`; its description says the link "opens the
  session in this app from outside it".
- `terminal-notifier … -open claude://claude.ai/epitaxy/local_<uuid>`: the user clicked the banner and the app switched to
  that session; that session's process, not running before, started at the click (its process age matched).
- host-differences H4 (2026-10-16): the desktop app's session message tool, called from inside a Claude session, wakes a
  stopped Claude session. Nothing outside the app can call it.

## Assumptions (confirmed by the user, 2026-11-26)

1. **Scope**: A (wording), B (session link: recorded at registration, opened by the notification click, title in the
   texts), C (only words: how a Claude sender may wake the recipient by hand when the user asks). No automatic waking.
2. **One module**, id `paused-session-link`, after `release-commands`; runtime change, so its release needs
   `upgrade --confirm`. The bridge version is set at release (D252).
3. **Where the link comes from**: a Claude session in the desktop app calls `get_session("self")` before
   `bridge_register` and passes its own link and title as a new optional field. The bridge accepts only a link of the
   form `claude://claude.ai/epitaxy/local_<uuid>` and a bounded title; it never reads the desktop app's files, logs or
   state. A registration without the field works as today (no click, no title).
4. **Interface 2.11 → 2.12** (an optional input field and an optional output field); **schema 7 → 8** (two columns on
   `agents`). ecosystem-lead gets the Spec first.
5. **Wording**: the bridge cannot tell paused from closed, so every text says "the Claude app paused it or it was
   closed" and asks for the session to be opened, with one sentence the sender can relay. Texts stay English, like all
   bridge text; the sending session translates for its user.
6. **Five minutes** before the notification, unchanged.
7. **Click**: with terminal-notifier and a recorded link, the offline notification opens the link; otherwise (no link,
   or the osascript fallback) there is no click, as today.
8. **Process**: Spec and Plan approved by the user before any code; Codex implements, the owner accepts.

## Decisions

- **D287 `bridge_register` takes `desktop: {link, title?}`.** Assumption 3.
  - Accepted only from a session whose verified host is Claude (`caller.host.app === "claude"`); from a Codex task, a
    script identity or a caller without a verified host it is refused with a sentence saying it is for Claude desktop
    sessions.
  - `link` must match `^claude://claude\.ai/epitaxy/local_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`;
    anything else is refused. `title` is optional: control characters removed, whitespace collapsed, trimmed, at most
    120 characters (longer is cut, not refused); empty means no title.
  - Omitted keeps what is stored (as `capabilities`); `null` clears it. A registration that moves the name to another
    session (`takeover`, or a new wake binding) clears it unless that call passes its own.
  - It is recorded, not proof: it opens a page in the user's own app and is shown as a name; it grants, binds and
    proves nothing (as D75's Codex `host`).
- **D288 storage.** Schema 8 adds `agents.desktop_link` and `agents.desktop_title` (TEXT, NULL). The migration only adds
  columns; old rows stay NULL. Readers of the schema number (bridge, CLI, hooks) move to 8 together.
- **D289 one wording for "not running".** Assumption 5. With a title the session is named `"<title>" (mailbox name
  <agent>)`, without one by `<agent>` alone. Shared sentence, used by the send warning, the outbox detail, the
  notification body and the expiry notice (each keeps its own first part):
  `The Claude app paused this session or it was closed; it reads its mailbox only after it is opened. Tell the user:
  "Open the Claude session <name> so it can read its waiting messages."`
  The notification title stays `agent-relay · <agent> is offline`; its subtitle gains the title when known.
- **D290 the offline notification opens the session.** Assumption 7. When the recipient has a stored link and the
  channel is terminal-notifier, the offline notice (D193 kind `offline`) gets `-open <link>`, built only from the stored,
  validated link. Other notice kinds, the osascript fallback and recipients without a link are unchanged.
- **D291 manual wake, in words only.** Assumption 1, C. When a link is stored, the send warning and the expiry notice
  (texts a sending model reads) add: `If the user asks to wake it now and you are a Claude session in the desktop app,
  you may send it one line with the app's session message tool to session local_<uuid>, asking it to read its mailbox.
  Do not do this unasked or repeatedly; the app may pause another session to make room.` The bridge calls nothing,
  opens nothing and never wakes a session itself.
- **D292 `bridge_agents` shows the link.** An agent entry carries `desktop: {link, title}` when stored, so a coordinating
  session can name or wake a stopped recipient without asking it. Retired short entries do not carry it.
- **D293 the skill asks for the link.** `skills/collab` (join step) and the server instructions: a Claude session that
  has the desktop app's `get_session` tool calls it with `"self"` first and passes `desktop: {link, title}`; a session
  without that tool (terminal Claude Code) omits it; never another session's link.

## Requirements

1. Red first (register tests): a Claude session's `desktop` is stored and read back; a bad link is refused; a long or
   control-character title is cleaned and cut; omitted keeps, `null` clears; takeover by another session clears it; a
   Codex task, a script identity and an unverified caller are refused.
2. Red first (schema): a schema-7 mailbox migrates to 8 with NULL columns and no data change; every schema reader in
   bridge, CLI and hooks accepts 8; a schema-8 mailbox opened by a schema-7 reader fails with the existing message.
3. Red first (texts): the send warning, `CLAUDE_NOT_RUNNING`, `noticeText` for `offline` and `CLAUDE_OFFLINE_EXPLANATION`
   carry D289's sentence, with the title when stored; D291's sentence appears in the send warning and the expiry notice
   only when a link is stored, and never in the user-facing notification.
4. Red first (notify, notice log): an offline notice for a recipient with a link has `-open <link>` as its click and the
   title in its subtitle; without a link, with the osascript channel or for other kinds, no `-open`; `notify.off` still
   silences it; no message body in it.
5. Red first (`bridge_agents`): an entry with a stored link carries `desktop`; without, none.
6. `interface.json` 2.12; `docs/collaboration-interface.md` §1 version line and the register/agents fields; bridge
   bookkeeping (`UPSTREAM.md` rows, `python3 -B scripts/bridge-manifest.py`); CHANGELOG `[Unreleased]`.
7. Docs: `skills/collab/SKILL.md` (D293); `docs/notifications.md` and `notifications.en.md` (clickable offline notice);
   `docs/host-differences.md` H1/H4 with the measured facts above (governor pause, link opens and restarts the session,
   notification `-open`).
8. `bash scripts/validate.sh` green; CI green.

## Boundaries

- Ask first: any test notice or test session on this Mac; anything on the real runtime, hosts or mailbox.
- Never: wake, start, resume or open a Claude session from the bridge; read the desktop app's logs, files or state;
  try to stop or work around the app's pausing; put a message body in a notification; accept a `desktop` field from a
  non-Claude caller.

## Acceptance (owner session, after release and upgrade)

- A test Claude desktop session registers with `desktop` (its own `get_session("self")`); `bridge_agents` shows it.
- The test session is stopped with the desktop app's own tool; a message to it returns D289's warning with its title and
  D291's sentence; after five minutes one notification arrives with the title, and clicking it opens that session, which
  then reads the message.
- A registration without `desktop` behaves as before (warning without title, no click).
- The result to ecosystem-lead names the new field, interface 2.12 and schema 8, for the release notice.

## Open questions

None.
