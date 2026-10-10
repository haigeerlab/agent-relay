# Spec: notice-location

## Objective

First module of 0.6.3 (bridge). The user, 2026-10-10 (relayed by the round-2 coordinator and confirmed by the user in
this session): a desktop notice shows that something waits but not where — "我现在只能看到通知但是我不太知道它是从哪个
命令行或者是哪个位置发出来的" — and clicking it does nothing. A notice must say which session, which project and where it
runs, and a click must bring that place to the front.

Readers: the user; the round-2 coordinator (reviews, re-checks after release).

## What exists today (main 72ee153, measured 2026-10-10)

- `bridge/src/notify.ts` `notifyUndelivered`: `terminal-notifier -title … -subtitle … -group agent-relay-<key>` with the
  body on stdin; no click action. Without terminal-notifier: `osascript display notification`, which has no click action.
  Two callers: a message Codex cannot receive now (`server.ts`, `wake-dispatcher.ts`) and a Claude session waiting for the
  user's approval (`wake-dispatcher.ts` `checkApprovals`, D148). `notify-preview.off` hides names and bodies (D89).
- terminal-notifier 3.1.0 has `-activate <bundle id>`, `-open <URL>`, `-execute <shell command>`; `-sender` is gone.
- Claude's session registry (`~/.claude/sessions/<pid>.json`) carries `entrypoint`, `kind`, `pid`, `cwd`, `name`,
  `hostSessionId`. On this Mac: desktop Code tab → `entrypoint: "claude-desktop"`, `kind: "interactive"`,
  `hostSessionId: "local_…"`, no tty; a terminal session → `entrypoint: "cli"`, `kind: "interactive"`, a tty from
  `ps -o tty= -p <pid>`. `claudeSessionsOrNull` reads the registry but keeps none of these three fields.
- Bundle ids: Claude desktop `com.anthropic.claudefordesktop` (registers `claude://`), ChatGPT/Codex `com.openai.codex`
  (registers `codex://`). Whether either scheme opens one session or thread is **not verified**.

## Assumptions (accepted by the user 2026-10-10)

1. **The text says where.** Both kinds of notice gain the session's name, its project folder's basename and one place:
   "Claude desktop app", "Terminal ttysNNN" (the terminal app's name when known), "background session — open with
   `claude attach <id>`", or "Codex app". The osascript fallback shows the same text. With `notify-preview.off` only the
   place category is shown, no session or project name. Length limits stay (names cut like today).
2. **Click actions, terminal-notifier only:**
   - Claude desktop session → `-activate com.anthropic.claudefordesktop`. A deep link to the session is used only if a
     real check while building (with the user's consent: it brings the app forward) shows it works; otherwise the app is
     only activated and no deep link is documented.
   - Terminal session → the owning app is found by walking the session process's parents (bounded depth) and taking
     the **outermost** `.app` on the first parent path that has one (so VS Code's "Code Helper.app" resolves to the
     enclosing `Visual Studio Code.app`). Its bundle id is read from that app's `Info.plist` and must match
     `^[A-Za-z0-9][A-Za-z0-9.-]{0,127}$`. For Terminal (`com.apple.Terminal`) and iTerm (`com.googlecode.iterm2`) — these two
     ids only — the click runs one fixed `-execute` command: `/usr/bin/open -b <that bundle id>` first, then
     `/usr/bin/osascript` with a fixed script that selects the tab whose tty matches and raises its window. macOS asks
     the user once for Automation permission, in terminal-notifier's name; if the user declines, the app is still
     brought forward by the `open` step and only the tab selection is missing. Any other app with a valid bundle id is
     only activated (`-activate <id>`; a read bundle id is never part of an `-execute` command). No `.app` in the
     parent chain (tmux, screen, ssh), or an unreadable or malformed bundle id → the text names the tty only, no click.
   - Background session → no click action (the user: text only).
   - Codex → the place is "Codex app", with `-activate com.openai.codex`, only when the bridge has just confirmed
     through the app's own socket (`~/.codex/ipc/ipc.sock`, held by ChatGPT.app — measured 2026-10-10) that the app
     holds this thread (`codexOwner` true). Otherwise (no connected owner, socket not reachable, no thread id, a Codex
     CLI) the text says "Codex" and there is no click action. A thread deep link only if the real check shows it works.
   - Place not determined (registry unreadable, session gone, off macOS) → today's notice, no click action.
3. **Security, fixed:** an `-execute` command or `-open` URL is built only from values the bridge verified itself and
   that match a strict format — pid (digits), tty (`ttys\d+`), session UUID, bundle id from a fixed list, fixed absolute
   program paths: exactly `/usr/bin/open` and `/usr/bin/osascript`. Session names, project paths, message bodies and
   sender names appear only in displayed text, never in a command line, script or URL. A click only brings a window
   forward: it approves nothing and types nothing. The tty is read only for a registry entry that still passes
   `claudeSessionsOrNull`'s own liveness check (pid and process start), so a reused pid is not followed.
   With `notify-preview.off` the text shows only the place category, yet the click still goes to the exact tab or app:
   that is intended — the switch hides names on screen, not where a click leads.
4. Notices are still only attempted (D76): the mark under `notified/`, deduplication and the "attempted" wording stay.
   Interface stays 2.0, mailbox schema 5; no new tool, no new configuration.
5. Vendored-bridge change: `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]` ("takes effect after `upgrade --confirm`"),
   README "授权与安全" gains two sentences (what a click does; the one-time Automation prompt is shown for
   terminal-notifier, and where in System Settings → Privacy & Security → Automation it can be changed).

## Decisions

- **D188 a notice says where the session is and a click goes there.** Assumptions 1–4.

## Requirements

1. Red first (bridge unit tests on pure functions): `locate(session, tty, owner)` → the four places and "unknown";
   notice text for each place, with and without preview; the argv for each place — `-activate` with the fixed bundle id,
   the `-execute` script for Terminal and for iTerm containing only the tty, nothing for background/unknown; a session
   name, cwd, body or sender containing quotes, `$(…)`, backticks and newlines never reaches argv outside `-title`,
   `-subtitle` and stdin; a tty or pid that fails its format drops the action; the only program paths in any argv are
   `/usr/bin/open` and `/usr/bin/osascript`; a nested `.app` path resolves to the outermost one; a parent chain with
   no `.app` gives tty-only text and no action; a malformed bundle id gives no action; a Codex notice without a
   confirmed app owner says "Codex" and has no action.
2. The registry reader keeps `entrypoint`, `kind`, `hostSessionId` (strings only, bounded); existing presence tests
   stay green.
3. Real check on this Mac, each recorded in the todo: an approval notice from a desktop session, from a Terminal tab and
   (if installed) an iTerm tab — the text names the place, the click raises the right window or tab; a Codex notice
   activates the ChatGPT app; what a click does after the Automation prompt was declined; the two deep links tried once
   with the user's consent.
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Ask first: opening `claude://` / `codex://` links and triggering test notices on this Mac.
- Never: put unverified text in a command or URL; answer a prompt; grant Automation permission for the user.

## Acceptance (coordinator, after 0.6.3)

- A notice from each place names it; clicking brings the right window or tab forward; nothing is approved by a click.

## Open questions

None. Accepted by the user on 2026-10-10; spec review by the round-2 coordinator pending.
