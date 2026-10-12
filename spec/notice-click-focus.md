# Spec: notice-click-focus

## Objective

Only module of 0.6.4 (bridge). From the round-2 coordinator's real-host acceptance of 0.6.3 (2026-10-10) and the user's
decision the same day ("按你的建议修，发 0.6.4"): clicking a terminal session's notice raises the right window but does
not make it the active one when the terminal app has several windows, so what the user types next goes to another
window. Scope is exactly two points; nothing else is added.

Readers: the user; the round-2 coordinator (reviews, re-checks after release).

## What exists today (main bee8d11, v0.6.3)

- `bridge/src/location.ts` `selectTab`: for Terminal the fixed script selects the tab whose tty matches, then
  `set index of w to 1`; for iTerm it runs `select w`, `select t`, `select s`. Both run after `/usr/bin/open -b <id>`.
- Measured by the coordinator with four Terminal windows, another window active and another app in front: after the
  click Terminal was frontmost and the target window was first in the window order, but the previously active window
  stayed the key window (its title-bar buttons lit; the target's grey). iTerm with several windows was not tested.
  The development check (#84) had one Terminal window with two tabs, where this cannot show.
- The approval notice's subtitle is `#id · agent · <session> in <project> · <place>`: with long names it passes 70
  characters and the place comes last. Whether macOS cuts it in the banner is not known (the user did not notice).

## Assumptions (accepted by the user 2026-10-10)

1. **Terminal:** after the tab is selected and the window ordered first, the fixed script also makes that window the
   active (key) window, so keyboard input lands in it. The exact statement (`set frontmost of w to true` is the
   coordinator's suggestion) is whichever the real check shows working with several windows.
2. **iTerm:** checked on this Mac with several windows first; fixed the same way only if it shows the same problem,
   otherwise left as it is.
3. **Unchanged security:** the script stays fixed and carries only the format-checked tty; the only program paths are
   `/usr/bin/open` and `/usr/bin/osascript`; a click only brings a window forward — it approves nothing and types
   nothing. No new permission is requested (Automation for Terminal and iTerm is the one 0.6.3 already asks for).
4. **Place in the subtitle:** a test notice of the same length is shown during the real check; if the banner cuts the
   place off, the place moves to the front of the subtitle (`<place> · #id · agent · <session> in <project>`, and the
   Codex notice likewise); if the place is visible, the text does not change.
5. Vendored-bridge change: `UPSTREAM.md`, manifest, CHANGELOG `[Unreleased]` ("takes effect after `upgrade --confirm`").
   Interface stays 2.0, mailbox schema 5.

## Decisions

- **D190 a clicked notice leaves the keyboard in the target window.** Assumptions 1–4.

## Requirements

1. Red first: the Terminal script contains the statement that makes the window active, after the tab selection; the
   existing assertions stay (only the tty varies; program paths exactly `/usr/bin/open` and `/usr/bin/osascript`;
   balanced quotes; hostile display names never in the command). The same for iTerm if assumption 2 finds the problem.
   If the place moves: subtitle tests for both notice kinds, with and without preview.
2. Real check on this Mac, each step asked first and recorded in the todo: with several windows of the terminal app,
   another window made active and another app in front, click the notice and type — the input must land in the target
   window. Terminal and iTerm each; also the single-window, two-tab case again (no regression).
3. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Ask first: every test notice and every step that moves windows on this Mac.
- Never: send keystrokes to a window from the script; widen what reaches the command line.

## Acceptance (coordinator, after 0.6.4)

- Several Terminal windows, another one active, another app in front: after clicking the notice the target window is
  the active window. The same for iTerm. Desktop-session and Codex notices as in 0.6.3.

## Open questions

None. Accepted by the user on 2026-10-10; spec review by the round-2 coordinator pending.
