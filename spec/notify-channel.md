# Spec: notify-channel

## Objective

The bridge's desktop notices (D67, worded "attempted" since D76) are shown with `osascript`, which macOS attributes to
Script Editor. On the user's Mac Script Editor has never asked for notification permission, so it is **not even listed**
in System Settings → Notifications and cannot be allowed: every notice is dropped (E2, found 2026-10-08). The same Mac has
Homebrew's `terminal-notifier`, which is allowed; its test banner was seen by the user. Use it when present, keep
`osascript` as the fallback, and make doctor judge the channel actually used. Decided by the user 2026-10-08; this
reverses D79's "terminal-notifier is not installed" for the case where it already is (no new dependency).

Readers: the user; the round-2 coordinator, who re-checks E1/E2 on the real host after 0.4.0.

## What exists today (measured on this Mac, 2026-10-08)

- `bridge/src/notify.ts` `notifyUndelivered`: exclusive mark file, then `execFile("osascript", [... text])`; off with
  `AGENT_RELAY_NOTIFY=off` or `notify.off`; `AGENT_RELAY_NOTIFY_LOG` records instead (tests).
- `/opt/homebrew/bin/terminal-notifier` → `../Cellar/terminal-notifier/2.0.0/bin/terminal-notifier`, a two-line bash
  script that `exec`s `…/terminal-notifier.app/Contents/MacOS/terminal-notifier "$@"`; owner `vilin`, mode `r-xr-xr-x`.
  `/usr/local/bin/terminal-notifier` does not exist here (that is the Intel Homebrew prefix).
- Notification Center prefs: `fr.julienxx.oss.terminal-notifier` `auth 7`, flags `0x2802056` (has `0x2000000`);
  `com.apple.ScriptEditor2` `flags 0x200e`, no `auth`.
- terminal-notifier 2.0.0 options include actions we must never use (`-execute`, `-open`, `-activate`, `-sender`,
  `-ignoreDnD`, `-appIcon`, `-contentImage`, `-sound`). It reads the message from **stdin** when `-message` is absent.
  Probe: the stdin message `-execute open -a Calculator⏎"-sender" (a,b) {x=1} [y]` was delivered verbatim (read back
  with `-list`), nothing ran (no Calculator), then removed with `-remove`.

## Assumptions

1. Only fixed paths, in order: `/opt/homebrew/bin/terminal-notifier`, `/usr/local/bin/terminal-notifier`. Never `PATH`.
   The candidate must resolve (all symlinks) to a regular, executable file owned by the current user or root and not
   writable by group or others; otherwise it is ignored (fallback to `osascript`).
2. Peer-controlled text never becomes an argument: the message goes on **stdin**; the arguments are exactly
   `-title agent-relay -group <group>`, with `<group>` built only from `agent-relay-` and the notice key reduced to
   `[A-Za-z0-9._-]` (anything else replaced by `_`). `execFile`, no shell. Newlines in the text become spaces (one-line
   banner); a leading `-` stays as text.
3. Interface unchanged (1.3): the notice text and the "attempted" wording (D76) stay; only the channel changes.
4. The bridge cannot see whether macOS shows a banner; "attempted" remains the honest wording on either channel.

## Decisions

- **D83 channel.** `notifyUndelivered` uses terminal-notifier (assumption 1) when found, else `osascript` as today.
  The channel search is a function that tests can point at a temporary directory (a parameter, never an environment
  variable, so nothing outside the code can redirect it).
- **D84 invocation.** Per assumption 2. A failing terminal-notifier run does not retry through `osascript` (that would
  notify twice when the first one did show); the mark stays, as today.
- **D85 permission check: where.** Option **A (recommended)**: the bridge only checks that terminal-notifier is
  present; doctor reports whether that channel appears allowed. Option B: the bridge also reads Notification Center
  prefs before every notice and falls back to `osascript` when terminal-notifier appears not allowed — more moving parts
  on the notice path, and on a Mac like this one the fallback is dropped anyway. With A, the map row's "且获准通知时"
  is corrected to "已安装（只认固定路径）时优先用它；doctor 判断它是否获准".
- **D86 group.** Option **per event (recommended)**: `-group agent-relay-<key>`, so every notice stays in Notification
  Center until dismissed. Option single: `-group agent-relay`, so only the latest notice is kept.
- **D87 doctor.** `notifications` judges the channel the bridge would use: terminal-notifier's entry
  (`fr.julienxx.oss.terminal-notifier`) when it is found, else Script Editor's. When neither can show: warn, and the next
  step says Script Editor cannot be allowed until it asks, so either install terminal-notifier (`brew install
  terminal-notifier`, the user's choice) or rely on the waiting list. `--test-notification` uses the same channel and
  says which.
- **D88 docs.** README notification paragraph, the collaboration-ops skill, CHANGELOG; spec `acceptance-030-gaps` D79
  gets a dated note pointing here.

## Requirements

1. Bridge tests, red first, with fake executables in a temporary directory:
   - a valid candidate is used with exactly `["-title", "agent-relay", "-group", "agent-relay-<key>"]` and the
     message on stdin; `osascript` is not called;
   - a sender name that starts with `-` and contains a newline arrives on stdin as one line, never in the arguments;
   - a key with characters outside `[A-Za-z0-9._-]` is reduced in the group;
   - a symlink to a group- or world-writable file, a non-executable file, a directory, or a missing candidate is
     ignored and `osascript` is used; `PATH` holding a `terminal-notifier` is never used;
   - the `notify.off` / `AGENT_RELAY_NOTIFY=off` switches and the once-per-key mark still hold.
2. Python tests: doctor `notifications` for terminal-notifier allowed / not allowed / never registered, Script Editor
   fallback states, and the next step when neither works; `--test-notification` calls the chosen channel once.
3. `UPSTREAM.md` row and manifest; docs per D88.
4. Validation: Python 3.9, 3.10, 3.14 locally; CI green on all four jobs.
5. Live check on this Mac (the user agreed to test banners): from a temporary runtime, one undelivered Codex message
   produces a terminal-notifier notice; read it back with `-list agent-relay-<key>` (title, message, group), then
   `-remove` it; `doctor` `notifications` → ok for terminal-notifier; `--test-notification` shows one banner the user
   confirms.

## Boundaries

- Always: fixed paths, stdin for text, `execFile`, the six forbidden options never used.
- Ask first: installing anything, any system setting; the real `~/.agent-relay`, `~/.claude`, `~/.codex`.
- Never: `PATH` lookup for the notifier; shell invocation; pushing without approval.

## Success criteria

Notices reach a banner on a Mac with terminal-notifier, verified by `-list`; hostile names cannot reach the argument
list; doctor tells the truth about the channel in use.

## Open questions

D85 (A recommended) and D86 (per event recommended).
