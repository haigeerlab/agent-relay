# Plan: acceptance-030-gaps

Based on [`spec/acceptance-030-gaps.md`](../../spec/acceptance-030-gaps.md) (accepted by the user on 2026-10-08:
assumptions 1–7, D72–D74). Branch `claude/unbound-recipient-warning` from main 631fa84. Red → green, one commit per
task.

## Task List

### Task 1: Warn when the recipient has no wake binding and no known host (D72)
Bridge test first (`test/notify.test.ts`, beside the D67 send-time test): a recipient registered from a Codex caller with
`wake: null` (no host) gets the D72 warning on `bridge_send`, and nothing is written to `AGENT_RELAY_NOTIFY_LOG`;
`wake: false`, a broadcast and a duplicate stay silent; a recipient with a recorded Claude host and no binding gets no
D72 warning. Red, then `server.ts` `bridge_send`. `UPSTREAM.md` row, `UPSTREAM.sha256` regenerated, CHANGELOG
`[Unreleased]` entry.
**Files:** `bridge/src/server.ts`, `bridge/test/notify.test.ts`, `bridge/UPSTREAM.md`, `bridge/UPSTREAM.sha256`,
`CHANGELOG.md`.

### Task 2: Same-second upgrade picks a suffixed stamp (D74)
Python test first (`hooks/test_runtime_upgrade.py`): with `backups/<stamp>/` already present for the frozen current
second, `upgrade --confirm` succeeds with backup, previous and stage all named `<stamp>-1`; all 100 names taken →
refused. Red, then `upgrade_runtime` (failed-upgrade directory uses the same suffix). CHANGELOG entry.
**Files:** `hooks/native_collaboration_runtime.py`, `hooks/test_runtime_upgrade.py`, `CHANGELOG.md`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 3: Live check in a temporary AGENT_RELAY_HOME/HOME, then the README paragraph (D73)
Install the runtime from this tree into a short temporary home; register a Codex-style identity with `wake: null` and
send to it from another identity: the D72 warning appears, no notice is shown. Run `install-codex
--approve-mailbox-tools` and `upgrade --confirm` within one second: the upgrade succeeds into `<stamp>-1`. Check
assumption 5 (which app macOS attributes `osascript` notifications to) on this Mac; then write the README paragraph next
to `notify.off` with what was observed. Evidence in the todo; temporary home moved to the Trash afterwards.
**Files:** `README.md`, `CHANGELOG.md`, `tasks/acceptance-030-gaps/todo.md`.

## Amendment 1 tasks (spec Amendment 1, accepted by the user on 2026-10-08: assumptions 8–12, D75, D75a, D76–D79)

### Task 4: Host claim without wake, granting nothing (D75, D75a)
Bridge tests first (`test/identity.test.ts` or a new `test/host-claim.test.ts`): `wake: null, host: {app: "codex",
sessionId}` records the host, no binding, no ping; refusals for a Claude caller, `app: "claude"`, a differing `wake`
target; another process registering the name with another thread (by `wake` or `host`) refused without `takeover`; a
process that did not register the name cannot send as it; `bridge_agents` `recordedHost.verified` false/true; a send to
the claimed recipient takes the D67 path. Red, then `server.ts` (`bridge_register` input, host choice, refusal hint),
`bridge_agents` `verified`. collab skill: a Codex task registering without wake passes `host` with its own
`CODEX_THREAD_ID`. `UPSTREAM.md`, manifest, CHANGELOG.
**Files:** `bridge/src/server.ts`, bridge tests, `skills/collab/SKILL.md`, `bridge/UPSTREAM.*`, `CHANGELOG.md`.

### Task 5: "Attempted", not "notified" (D76)
Update the D67 tests to expect the D76 text first (red), then `NOTIFIED_TEXT` in `notify.ts`; README D73 paragraph says
"attempted" and points to the waiting list and the doctor check. `UPSTREAM.md`, manifest, CHANGELOG.
**Files:** `bridge/src/notify.ts`, `bridge/test/notify.test.ts`, `bridge/test/codex-gate.test.ts` (if it names the
text), `README.md`, `bridge/UPSTREAM.*`, `CHANGELOG.md`.

### Task 6: Waiting list in bridge_agents, doctor and collab (D77)
Bridge test first: `waiting: {count, from, ids}` for a Codex-host recipient (acknowledged, failed, expired excluded;
none for Claude hosts; ids capped at 20). Python test first: doctor `codex-waiting` ok none / ok list / warn when a
listed message is older than 10 minutes. Then `bridge-store.ts`/`server.ts` and `native_collaboration_doctor.py`;
collab skill answers "等 Codex 处理的消息" from `bridge_agents`. `UPSTREAM.md`, manifest, CHANGELOG.
**Files:** `bridge/src/bridge-store.ts`, `bridge/src/server.ts`, bridge test, `hooks/native_collaboration_doctor.py`,
`hooks/test_doctor.py`, `skills/collab/SKILL.md`, `bridge/UPSTREAM.*`, `CHANGELOG.md`.

### Task 7: Doctor notification check and --test-notification (D78)
Python tests first, from fake `defaults export` plist bytes: off by choice (`notify.off`, env), never registered, appears
not allowed (no `auth`; no `0x2000000`), appears allowed, cannot read, not macOS; `--test-notification` calls
`osascript` once with the fixed text and plain `doctor` never does. Then the doctor check and CLI flag; README and the
collaboration-ops skill mention it. CHANGELOG.
**Files:** `hooks/native_collaboration_doctor.py`, `hooks/native_collaboration_runtime.py` (CLI flag),
`hooks/test_doctor.py`, `README.md`, `skills/collaboration-ops/SKILL.md`, `CHANGELOG.md`.

### Task 8: Interface 1.3 and docs
`interface.json` 1.3 and its tests; `docs/collaboration-interface.md` (register `host`, `bridge_agents` `waiting` and
`recordedHost.verified`, D76 wording); spec D79 evaluation referenced from the CHANGELOG.
**Files:** `interface.json`, its tests, `docs/collaboration-interface.md`, `CHANGELOG.md`.

### Checkpoint (report): validate on Python 3.9, 3.10, 3.14 + bridge `npm run check`

### Task 9: Live check 2 in a temporary AGENT_RELAY_HOME/HOME, then on this Mac read-only
Temporary home with the runtime installed from this branch: a Codex-style client registers with `host` and `wake:
null`; a send to it shows the D76 warning and `AGENT_RELAY_NOTIFY_LOG` gets one line; `bridge_agents` lists `waiting`;
`doctor` shows `codex-waiting`. On this Mac: `doctor` `notifications` reads the real Script Editor entry (read only) and
`doctor --test-notification` runs once for the user to confirm whether a banner appears. Evidence in the todo;
temporary home to the Trash.

### Checkpoint (gate): module review
