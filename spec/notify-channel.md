# Spec: notify-channel

## Objective

The bridge's desktop notices (D67, worded "attempted" since D76) are shown with `osascript`, which macOS attributes to
Script Editor. On the user's Mac Script Editor has never asked for notification permission, so it is **not even listed**
in System Settings → Notifications and cannot be allowed: every notice is dropped (E2, found 2026-10-08). The same Mac has
Homebrew's `terminal-notifier`, which is allowed; its test banner was seen by the user. Use it when present, keep
`osascript` as the fallback, and make doctor judge the channel actually used. Decided by the user 2026-10-08; this
reverses D79's "terminal-notifier is not installed" for the case where it already is (no new dependency).

The user also asked (via the round-2 coordinator, 2026-10-08) that a notice say **what** the work is: today it shows
only the sender and the message number, which does not work as a reminder. So a notice now shows a short preview of the
message by default. This **reverses D67's "never the body"** and needs the user's explicit confirmation (D89).

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
  with `-list`), nothing ran (no Calculator), then removed with `-remove`. Titles passed as arguments with a fixed
  `agent-relay · ` prefix came back verbatim (`agent-relay · "x" (a,b) {k=v} -execute y → Codex`, `… ;rm -rf ~ …`), and a
  stdin body `(a,b)` stayed text (not parsed as a property list).
- terminal-notifier 3.1.0 (Homebrew stable since 2026-08-30; the user may upgrade) keeps `-title`, `-subtitle`,
  `-group` and still takes the body from stdin ("the piped text then becomes the body", its README).
- Agent names are free text (trimmed, at most 128 characters; `addressing.ts` `agentNameProblem`).

## Assumptions

1. Only fixed paths, in order: `/opt/homebrew/bin/terminal-notifier`, `/usr/local/bin/terminal-notifier`. Never `PATH`.
   The candidate must resolve (all symlinks) to a regular, executable file owned by the current user or root and not
   writable by group or others; otherwise it is ignored (fallback to `osascript`).
2. Only options present since 2.0 and unchanged in 3.1: `-title`, `-subtitle`, `-group`; the body goes on **stdin**
   (not `-message`), so the message preview, the most attacker-shaped text, is never an argument at all. The sender and
   recipient names do reach `-title` / `-subtitle`, always after a fixed prefix (`agent-relay · `, `#<id> · `) so a value
   can never start with `-`, and cleaned as in D89. `<group>` is `agent-relay-` plus the notice key reduced to
   `[A-Za-z0-9._-]` (anything else becomes `_`). `execFile`, no shell. (The coordinator suggested `-message` with
   escaping; stdin needs no escaping and works on both versions, so it is used instead.)
3. Interface unchanged (1.3): the "attempted" wording in wake details and send warnings (D76) stays; only what the
   desktop notice itself shows and how it is sent change.
4. The bridge cannot see whether macOS shows a banner; "attempted" remains the honest wording on either channel.

## Decisions

- **D83 channel.** `notifyUndelivered` uses terminal-notifier (assumption 1) when found, else `osascript` as today.
  The channel search is a function that tests can point at a temporary directory (a parameter, never an environment
  variable, so nothing outside the code can redirect it).
- **D84 invocation.** Per assumption 2. A failing terminal-notifier run does not retry through `osascript` (that would
  notify twice when the first one did show); the mark stays, as today.
- **D85 permission check: where.** **A (chosen by the user 2026-10-08)**: the bridge only checks that terminal-notifier is
  present; doctor reports whether that channel appears allowed. Option B: the bridge also reads Notification Center
  prefs before every notice and falls back to `osascript` when terminal-notifier appears not allowed — more moving parts
  on the notice path, and on a Mac like this one the fallback is dropped anyway. With A, the map row's "且获准通知时"
  is corrected to "已安装（只认固定路径）时优先用它；doctor 判断它是否获准".
- **D86 group.** **Per event (chosen by the user 2026-10-08)**: `-group agent-relay-<key>`, so every notice stays in Notification
  Center until dismissed. Option single: `-group agent-relay`, so only the latest notice is kept.
- **D87 doctor.** `notifications` judges the channel the bridge would use: terminal-notifier's entry
  (`fr.julienxx.oss.terminal-notifier`) when it is found, else Script Editor's. When neither can show: warn, and the next
  step says Script Editor cannot be allowed until it asks, so either install terminal-notifier (`brew install
  terminal-notifier`, the user's choice) or rely on the waiting list. `--test-notification` uses the same channel and
  says which.
- **D89 preview by default (reverses D67's "never the body"; confirmed by the user 2026-10-08).** A notice about a
  message shows: title `agent-relay · <sender> → Codex`; subtitle `#<id> · <recipient> · <reason>` (D89a); body the first 60 characters
  (code points) of the message, with every control character (C0, C1, DEL, U+2028, U+2029) turned into a space, runs of
  whitespace collapsed to one, trimmed, and `…` appended when cut. Names in the title and subtitle get the same cleaning
  and are cut at 40 characters with `…`; a missing sender is `a peer`. A leading `-` in the body needs no escaping
  (stdin) and stays visible. The gate-off notice (no message) keeps its text as the body, title `agent-relay · gated
  Codex wake off`. With `notify-preview.off` next to the mailbox the old form returns: title `agent-relay`, body the D67
  text without any message content. `osascript` (fallback) shows the same title, subtitle and body (still passed as
  argv items, never in the script). README: the preview appears on the lock screen and when the screen is shared
  (macOS "Show previews" can limit that), and how to turn it off.
- **D89a the reason stays visible (found in Task 1, chosen by the user 2026-10-08, option A).** The preview took the
  body that used to carry the reason, including the one that asks the user to act ("gated Codex wake is off; check
  Codex, then delete codex-gate.off …"). The subtitle therefore ends with the reason, cleaned like a name and cut at 80
  characters with `…`. Reasons are fixed texts written by the bridge, never peer text. The gate-off notice keeps
  subtitle `#<id> · <recipient>` and its text as the body. (Option B, reason instead of preview only for notices that
  need action, was not chosen.)
- **D88 docs.** README notification paragraph, the collaboration-ops skill, CHANGELOG; spec `acceptance-030-gaps` D79
  gets a dated note pointing here.

## Requirements

0. Bridge tests for D89, red first: preview cut at 60 code points with `…` (and not cut at exactly 60); newline, tab,
   other control characters and U+2028 become single spaces; a body starting with `-` arrives on stdin unchanged; a
   sender with quotes, newline, `-` first and over 40 characters is cleaned and cut in the title and never starts an
   argument; `notify-preview.off` gives the old title and body with no message content; the gate-off notice keeps
   its text.
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

None. Accepted by the user on 2026-10-08: assumptions 1–4, D83–D89 with D85 = A, D86 = per event, D89 confirmed.
