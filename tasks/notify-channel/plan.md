# Plan: notify-channel

Based on [`spec/notify-channel.md`](../../spec/notify-channel.md) (accepted by the user on 2026-10-08: assumptions 1–4,
D83–D89; D85 = A, D86 = per event, D89 confirmed). Branch `claude/notify-channel` from main 38df90e. Red → green, one
commit per task. The last module before 0.4.0.

## Task List

### Task 1: what a notice shows (D89)
Bridge tests first (`test/notify.test.ts`): a pure `noticeFields(notice, { preview })` gives title `agent-relay ·
<sender> → Codex`, subtitle `#<id> · <recipient>`, body = cleaned preview; cut at 60 code points with `…` (exactly 60
not cut); newline, tab, other C0/C1, DEL, U+2028/2029 → one space; runs collapsed, trimmed; a body starting with `-`
unchanged; names with quotes, newline, leading `-`, over 40 characters cleaned and cut; missing sender `a peer`;
`notify-preview.off` → title `agent-relay`, body the D67 text, no message content; the gate-off notice keeps its text.
Then `notify.ts` (notice carries the message body; callers in `wake-dispatcher.ts` and `server.ts` pass it). The
existing "never the body" assertions become "body only as the cleaned preview, none with the switch". `UPSTREAM.md`,
manifest, CHANGELOG.

### Task 2: the channel (D83, D84, D86)
Bridge tests first with fake executables in a temporary directory (candidate list passed as a parameter): a valid
candidate is run with exactly `-title <t> -subtitle <s> -group agent-relay-<key>` and the body on stdin, `osascript` not
called; key characters outside `[A-Za-z0-9._-]` become `_`; a symlink to a group/world-writable file, a non-executable
file, a directory, a missing file → `osascript`; a `terminal-notifier` on `PATH` is never used; a failing notifier is
not retried through `osascript`; `notify.off` / `AGENT_RELAY_NOTIFY=off` / the once-per-key mark still hold. Then
`notify.ts` (`findNotifier`, the two senders; real candidates `/opt/homebrew/bin`, `/usr/local/bin`). `UPSTREAM.md`,
manifest, CHANGELOG.

### Task 3: doctor judges the channel in use (D87)
Python tests first: with terminal-notifier found (fake candidate) its entry decides — allowed ok / not allowed / never
registered warn; without it, the Script Editor states as today plus the next step (Script Editor cannot be allowed until
it asks; `brew install terminal-notifier` is the user's choice; the waiting list); the check names the channel;
`--test-notification` runs the chosen channel once (terminal-notifier with the body on stdin) and says which. Then
`native_collaboration_doctor.py`. CHANGELOG.

### Task 4: docs (D88)
README notification paragraph (channel, preview on by default, shown on the lock screen and when sharing the screen,
macOS "Show previews", `notify-preview.off`); collaboration-ops skill; `acceptance-030-gaps` spec D79 dated note;
`docs/collaboration-interface.md` notice row; CHANGELOG `[Unreleased]` summary.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 5: live check on this Mac
Runtime from this branch in a temporary HOME: one message to an unbound Codex-host identity → a terminal-notifier
notice; read back with `terminal-notifier -list agent-relay-<key>` (title, subtitle, cleaned preview, group), then
`-remove`; a sender name starting with `-` and containing a newline shows cleaned; with `notify-preview.off` the old
form. On this Mac (read only): doctor `notifications` names terminal-notifier and is ok; `--test-notification` once,
the user confirms the banner. Temporary home to the Trash.

### Checkpoint (gate): module review
Then push and PR; CI must be green on all four jobs; the coordinator is told when it merges (last module for 0.4.0).
