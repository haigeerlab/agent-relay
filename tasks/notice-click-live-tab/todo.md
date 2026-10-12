# Todo: notice-click-live-tab

- [x] Task 1: red test, then the Terminal match (`and (count of processes of t) > 0`) — red (the old match line), green with the one line; the iTerm match line is asserted unchanged
- [x] Task 2: real checks 2026-10-12 — I set the windows up with AppleScript (asked first) and read `id`/`tty`/process count/`miniaturized`/`index` before and after; the user clicked each banner; notices built by the worktree's code
  - Check 1, kept scene (312683 live ttys004; 316414 ended, ttys008; 316500 live ttys008, minimized; order 312683, 316414, 316500), process condition only: the live 316500 was restored — the match is right — but the ended 316414 ended up first and frontmost. Cause: `w` is "window N" and the restore reorders the windows (316500, 312683, 316414), so `set index`/`set frontmost` hit the new window 3. Present since #91. Fix (spec assumption 4a, the user: "iTerm 也一起改"): pin the window by id; red test first for both scripts.
  - Check 2 (316414 had been closed meanwhile, not by me; two windows, target 316500 minimized): restored and first.
  - Scene rebuilt (asked first) with `open -a Terminal` on a script that exits (316613, ended, ttys002) and then one that sleeps (316615, live, got the freed ttys002). This shows the mechanism: an ended tab keeps reporting its own tty, and the system hands that tty to the next session.
  - Check 3, target 316615 minimized, order 312683, 316613 (ended), 316500, 316615: after the click 316615 restored and first; 316613 third, not raised.
  - Check 4, target not minimized, order 312683, 316613 (ended), 316615, 316500, another app in front: after the click 316615 first; 316613 third.
  - Check 5, iTerm, target window 308067 minimized and second, its current tab ttys010, target session ttys000: after the click iTerm frontmost, 308067 restored and first, current tab ttys000.
  - In checks 2–4 the user had switched back to the Claude app before I read the state, so Terminal's `frontmost of window` read false; "first in the window order" is what was read. Not checked: iTerm with three or more windows.
- [x] Task 3: bridge bookkeeping — `UPSTREAM.md` row, manifest, CHANGELOG `[Unreleased]` (both changes; known issue for an ended iTerm session kept open)
- [x] Checkpoint (report): local validation — `scripts/validate.sh` pass on Python 3.9.6, 3.10.7, 3.14.3 with Node v24.18.0 first on PATH: 47 files / 770 tests each, bridge `npm run check` included
- [x] Task 4: PR and CI — #93 (4e56604 code, aa1891b wording of the mechanism after the review), the four CI jobs green
- [x] Checkpoint (gate): module review — the round-2 coordinator reviewed #93 (code and tests accepted; asked for the mechanism wording in the CHANGELOG and the spec to be corrected: aa1891b; will re-read `frontmost` and try three windows in the acceptance); the user merged #93 (5f7c893)
