# Spec: notice-click-live-tab

## Objective

Only module of 0.6.5 (bridge). From the round-2 coordinator's real-host acceptance of 0.6.4 (2026-10-12) and the
user's decision the same day ("现在修，发 0.6.5"): clicking a terminal session's notice acted on the wrong Terminal
window, because a tab whose process had ended reported the same tty as the live session and the fixed script takes
the first match. Scope is exactly this one point.

Readers: the user; the round-2 coordinator (reviews, re-checks after release).

## What exists today (main 2cebc86, v0.6.4)

- `bridge/src/location.ts` `selectTab`: the Terminal script walks windows and tabs and acts on the first tab with
  `tty of t is "/dev/<tty>"`, then returns. The iTerm script does the same over sessions.
- Measured on this Mac 2026-10-12 (read-only AppleScript, by the coordinator and again here):

  | Terminal window | tty | busy | processes | note |
  |---|---|---|---|---|
  | 312683 | /dev/ttys004 | true | 4 | live |
  | 316414 | /dev/ttys008 | false | 0 | "[进程已完成]", opened earlier on ttys007 |
  | 316500 | /dev/ttys008 | true | 5 | the target (live claude session), minimized |

  `ps -t ttys007` now shows iTerm's login: the ended tab's old tty was reused by the system, and Terminal reports
  ttys008 for it. So the tty of an ended Terminal tab cannot be trusted. The click restored 316414 and left 316500
  minimized.
- The same loop with `and (count of processes of t) > 0` matches only 316500 (measured here, read-only).
- Not introduced by 0.6.4: the 0.6.3 script picks the same wrong tab; no earlier check had a duplicate tty.
- iTerm: its `session` class has `tty`, `is processing` and `is at shell prompt`, no process list. Both profiles on
  this Mac have "Close Sessions On End = true", so an ended session leaves no tab behind.

## Assumptions (accepted by the user 2026-10-12; iTerm stays unchanged)

1. **Terminal:** the match becomes `tty of t is "/dev/<tty>" and (count of processes of t) > 0`. A live tab always
   has at least its login process; an ended one has none. Everything after the match is unchanged (select the tab,
   restore if minimized, order first, make key).
2. **No fallback to an ended tab:** when no tab with processes matches, the script does nothing more than 0.6.4 does
   when no tty matches (the app was already brought forward by `open -b`). An ended tab is never the session.
3. **iTerm is left as it is.** With the default "close sessions on end" no ended session remains, and its scripting
   dictionary has no process count to test. What a kept ended session (that setting turned off) reports as its tty is
   **not measured**: measuring it means changing the user's iTerm profile. Recorded in the CHANGELOG's known issues.
4. **Unchanged security:** the script stays fixed and carries only the format-checked tty; program paths are exactly
   `/usr/bin/open` and `/usr/bin/osascript`; a click only brings a window forward. No new permission: `processes` is
   read through the Automation grant for Terminal that 0.6.3 already asks for (the read worked here without a prompt).
4a. **Added while building (the user, 2026-10-12: "iTerm 也一起改"):** the target window is pinned by its id before
   anything moves. Found in this module's first real check: `w` in `repeat with w in windows` is "window N", and
   restoring a minimized window reorders the windows, so the statements after the restore (`set index`,
   `set frontmost`; iTerm's `select w`) acted on whichever window was then in that position — with three Terminal
   windows the ended one came to the front although the live one had been matched and restored. Present since 0.6.4
   (#91), whose checks had two windows. Both fixed scripts now run `set x to window id (id of w)` right after the
   match and use `x` afterwards. The command still carries only the tty. This is the only iTerm change; assumption 3
   (no process condition for iTerm) stands.
5. Vendored-bridge change: `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]` ("takes effect after
   `upgrade --confirm`"). Interface stays 2.0, mailbox schema 5, delegation store schema 3.

## Decisions

- **D191 a clicked terminal notice acts only on a tab that still has processes, and on the window it matched.**
  Assumptions 1–3 and 4a.

## Requirements

1. Red first: the Terminal script's match line is exactly
   `if tty of t is "/dev/<tty>" and (count of processes of t) > 0 then`; the existing assertions stay (statement
   order after the match; only the tty varies; program paths; balanced quotes; hostile names never in the command).
   The iTerm script is asserted unchanged.
2. Real check on this Mac with the kept scene (ended window 316414 reporting the target's tty), each step asked first
   and recorded in the todo: click the notice with the target minimized, and again with it not minimized and another
   window active — each time the live session's window becomes the active one and 316414 is not touched.
3. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Ask first: every test notice and every step that moves windows on this Mac.
- Never: send keystrokes to a window from the script; widen what reaches the command line; change the user's iTerm
  or Terminal settings to build a test scene.

## Acceptance (coordinator, after 0.6.5)

- With an ended Terminal tab reporting the same tty as a live session, clicking that session's notice activates the
  live session's window, minimized or not. The 0.6.4 points (several windows, minimized target, place first in the
  subtitle) still hold.

## Open questions

None. Accepted by the user on 2026-10-12; spec review by the round-2 coordinator pending.
