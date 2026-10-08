# Spec: acceptance-030-gaps

## Objective

Close three small gaps found while accepting and installing 0.3.0 (2026-10-08):

1. **E1** (round-2 end-to-end acceptance, thread 01a119c6…): a Codex identity registered with `wake: null`
   (`ar-acc-e2e-cx2`) has no recorded host, so the bridge does not know it is Codex. Messages #160 and #161 to it queued
   silently: no desktop notification, no warning to the sender.
2. **Banner**: the coordinator could not confirm a desktop banner appeared. `notify.ts` shows it through `osascript`, and
   macOS shows such notifications only if the app they are attributed to may notify. The README does not say so.
3. **Backup collision** (real-host 0.3.0 upgrade): `install-codex --approve-mailbox-tools` followed within the same
   second by `native_collaboration_runtime.py upgrade --confirm` fails with "an upgrade with this timestamp already
   exists; retry in a second", because both create `backups/<UTC second>/`.

Readers: the user; the coordinator ("第二轮联调") who re-checks E1 on the real host.

## What exists today (measured, main 631fa84, 2026-10-08)

- `bridge/src/server.ts:182`: on `bridge_register`, the recorded host is the caller's verified host (Claude) or, for
  Codex, the claimed `wake` target. A Codex caller with `wake: null` records no host. That is by design: the bridge
  never guesses a thread.
- `bridge/src/server.ts:277`: `bridge_send` warns and notifies only when the recipient's recorded host is Codex and it
  has no wake binding (D67). A recipient with no host and no binding gets nothing; `wake` in the result is `null`.
- `hooks/native_collaboration_runtime.py:410-416`: `upgrade_runtime` names `backups/<stamp>`,
  `.runtime-upgrade-<stamp>` and `runtime.previous-<stamp>` with a one-second `%Y%m%dT%H%M%SZ` stamp and refuses if
  any exists.
- `hooks/host_backup.py:55-59`: `backup_host_files` already handles the same collision by trying `<stamp>`, then
  `<stamp>-1` … `<stamp>-99`.
- README line 92-94 describes the notifications and `notify.off`, nothing about macOS permission.

## Assumptions

1. E1's fix is a warning only. The bridge still never infers a host without a claimed thread id, and sends no desktop
   notification for such a recipient: it does not know whom to notify.
2. The warning applies only when the recipient has **no wake binding and no recorded host**. A recipient with a recorded
   Claude host but no binding (for example a `claude -p` helper that uses `bridge_wait`) stays silent as today; the
   Codex case keeps its D67 notice.
3. No warning for broadcasts (`to: "*"`), for duplicates, or when the sender passed `wake: false` (they chose not to
   wake it).
4. Warnings are already part of the send result; adding one is not an interface change. `interface.json` stays 1.2.
5. `osascript`'s `display notification` is attributed to Script Editor (脚本编辑器) in System Settings → Notifications.
   To be confirmed in the live check on this Mac before the README text is final.
6. The backup fix follows `host_backup.py`'s convention: `<stamp>`, then `<stamp>-1`, `<stamp>-2` …; one suffix is
   chosen so the backup, stage and previous directories still share it.
7. Release number is decided at release.

## Decisions

- **D72 unbound, host-unknown recipient warning.** `bridge_send` adds
  `"<to>" has no wake binding and no known host; it sees this message only when it reads its inbox.` under the
  conditions of assumptions 2 and 3. No desktop notification, no change to delivery.
- **D73 README notification permission.** Next to the `notify.off` paragraph: if no banner appears, allow
  notifications for Script Editor (脚本编辑器) in System Settings → Notifications; the wake detail and the sender's
  warning still say the user was notified, because the bridge cannot see whether macOS showed it.
- **D74 upgrade stamp suffix.** `upgrade_runtime` picks the first of `<stamp>`, `<stamp>-1` … `<stamp>-99` for which
  none of the three directories exists, and refuses only if all 100 are taken. The failed-upgrade directory uses the
  same suffix.

## Requirements

1. Bridge test, red first: a recipient registered with `wake: null` from a Codex caller (no host) gets the D72 warning
   on `bridge_send`; no notice is logged (`AGENT_RELAY_NOTIFY_LOG`); `wake: false` and broadcast stay silent.
2. Bridge test: a recipient with a recorded Claude host and no binding gets no D72 warning; the D67 Codex warning is
   unchanged (existing `notify.test.ts` still passes).
3. Python test, red first: with `backups/<stamp>/` already present for the current second, `upgrade --confirm`
   succeeds into `<stamp>-1` for the backup, previous and stage names; existing `test_runtime_upgrade.py` still passes.
4. README paragraph (D73); `UPSTREAM.md` row and `UPSTREAM.sha256` regenerated for the bridge change; CHANGELOG
   `[Unreleased]` entries.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; bridge `npm run check` green.
6. Live check in a temporary `AGENT_RELAY_HOME`/HOME: install the runtime from this tree, register a Codex-style
   identity with `wake: null`, send to it, see the warning; run `install-codex --approve-mailbox-tools` and
   `upgrade --confirm` in the same second and see the upgrade succeed. Check assumption 5 on this Mac.

## Boundaries

- Always: temporary homes for live checks; backups stay 0700/0600.
- Ask first: the real `~/.agent-relay`, `~/.claude`, `~/.codex`; anything on the real host.
- Never: infer a Codex thread id; push without approval.

## Success criteria

The new tests are red before and green after; validation green on the three Pythons and the bridge; the live check
shows the warning and a same-second upgrade succeeding.

## Open questions

None, once assumptions 1–7 are confirmed.

## Amendment 1 (2026-10-08): E1 host claim and E2 notification visibility

Tasks 1–3 (D72–D74) are done and stay. The round-2 coordinator then reported **E2** from the real host: the 12:34 held
notice never appeared, and a direct `osascript … display notification` returned 0 with no banner. The bridge still
wrote its `notified` mark and told the sender "The user was notified on this Mac", which is unfounded: the message can
again wait unseen. The user chose (2026-10-08): E1 option A below, E2 items a–c in this module, CI as a separate module
after this one.

### Measured (this Mac, 2026-10-08)

- `identity.ts:11`: Claude puts its session id in the bridge's environment (verified host); the Codex app-server does
  not. A Codex task's thread id reaches the bridge only as the `wake` target it claims (`server.ts:182`).
- `skills/collab/SKILL.md` registers with `wake: null` by default, so E1 is the normal Codex path, not an edge case.
- Notification Center prefs (`defaults export com.apple.ncprefs`, read only), entry `com.apple.ScriptEditor2`:
  `flags = 0x200e`, no `auth` key. Apps that do show notifications here have an `auth` value and flag bit `0x2000000`
  (Claude `0x12802056` auth 7, Mail `0x1280000e` auth 1, Calendar `0x32882016` auth 263). Likely cause of E2: Script
  Editor was never allowed to notify. The format is undocumented.
- `bridge_agents` already returns unread counts per agent; doctor already reads a private copy of the mailbox.

### Assumptions (amendment)

8. A Codex task's own `CODEX_THREAD_ID`, passed as a host claim, is trusted exactly as much as the same id passed as a
   `wake` target today; nothing else is inferred (option B, "not Claude so Codex", rejected).
9. "Waiting for Codex" = direct messages to a non-retired agent whose recorded host is Codex, not acknowledged by it,
   delivery state not `failed` or `expired`. Bodies are never shown; only count, senders and ids (at most 20 ids).
10. The Script Editor reading in doctor is best effort: the plist format is undocumented, so doctor says "appears" and
    always offers a visible test notification as the real check. Focus modes cannot be read; doctor says so.
11. New `bridge_register` input and a new `bridge_agents` field are compatible additions: interface 1.2 → **1.3**.
12. E2 item d (other channels) is an evaluation in this spec only, no code.

### Decisions (amendment)

- **D75 host claim without wake.** `bridge_register` takes an optional `host: {app: "codex", sessionId}`. It records
  the Codex host and binds nothing. Refused when the caller has a verified host (a Claude session), when `app` is not
  `codex`, or when a `wake` target is also given and differs. Ownership rules are unchanged: the recorded host is the
  owner, and another session's name still needs `takeover`. With a recorded Codex host and no binding, sends take the
  D67 path (notice attempted + sender warning); D72 stays the fallback when no host is known. The collab skill tells a
  Codex task to pass `host` with its own `CODEX_THREAD_ID` whenever it registers without wake; the refusal hint for a
  re-register without it names `host` as well as `wake`.
- **D76 "attempted", not "notified".** `NOTIFIED_TEXT` and every use (wake detail, send warning) become: `A desktop
  notification was attempted on this Mac; macOS may not show it (Script Editor notifications off, or Focus). The user
  can list waiting messages with doctor or by asking any session.` The `notified/` marks keep deduplicating. README
  (the D73 paragraph) says "attempted" and points to the waiting list and the doctor check.
- **D77 waiting list.** `bridge_agents` adds `waiting: {count, from, ids}` to each agent with a recorded Codex host
  and at least one waiting message (assumption 9). Doctor adds check `codex-waiting`: ok with "none" or the list;
  **warn** when any listed message is older than 10 minutes (the D67 busy threshold), with the next step "open that
  Codex task, or ask the sender". The collab skill: when the user asks what is waiting (等 Codex 处理的消息), call
  `bridge_agents` and report `waiting` per agent.
- **D78 notification check.** Doctor adds check `notifications`: ok "off by choice" when `notify.off` exists or
  `AGENT_RELAY_NOTIFY=off`; warn "never registered" when Script Editor has no entry; warn "appears not allowed" when
  it has no `auth` value or lacks flag `0x2000000`; ok "appears allowed (a Focus mode can still hide banners)"
  otherwise; warn "cannot read" on any read error; not on macOS → ok "not macOS, no desktop notifications". Each warn
  says: System Settings → Notifications → Script Editor (脚本编辑器) → Allow Notifications, then
  `native_collaboration_runtime.py doctor --test-notification`. `--test-notification` shows one notification with
  the fixed text "agent-relay test notification" through the same `osascript` call and prints "Did a banner appear?
  If not, see the notifications check." It never runs without the flag.
- **D79 other channels (evaluation, no code).**
  - Codex app's own notices: they come from the Codex turn, which needs a wake; useless exactly when the wake was held
    or Codex is offline.
  - `display alert` / dialog via `osascript`: visible without notification permission, but modal and focus-stealing
    from a background process; rejected.
  - Third-party `terminal-notifier`: not installed and a new dependency; rejected.
  - A notice to the sender's own mailbox: already done (warnings, bridge notices), but the sender is an agent, not the
    user.
  - Recommendation: the pull channel (D77 waiting list in doctor and any session) is the one the user can always see;
    the push notice stays best effort with honest wording (D76).

### Requirements (amendment)

7. Bridge tests, red first: register with `wake: null, host: {app: "codex", sessionId}` records the host and no binding;
   a send to it attempts a notice and warns with the D76 text; refusals for a Claude caller, `app: "claude"`, and a
   different `wake` target; a recipient with no host still gets D72.
8. Bridge test: the D76 text replaces "The user was notified" in send warnings and wake details (existing D67 tests
   updated to the new text).
9. Bridge test: `bridge_agents` `waiting` for a Codex-host recipient (count, senders, ids; acknowledged, failed and
   expired excluded; none for Claude hosts). Python test: doctor `codex-waiting` ok / list / warn after 10 minutes.
10. Python tests: doctor `notifications` for each state, from a fake `defaults export` output; `--test-notification`
    calls `osascript` once with the fixed text and is never called by plain `doctor`.
11. collab skill and README updated; `interface.json` 1.3 and `docs/collaboration-interface.md`; `UPSTREAM.md` rows and
    `UPSTREAM.sha256`; CHANGELOG.
12. Validation on Python 3.9, 3.10, 3.14 and bridge `npm run check`; live check in a temporary home: host claim →
    D67 warning with D76 text, `bridge_agents` waiting, doctor `codex-waiting`; on this Mac, `doctor` `notifications`
    reads the real Script Editor entry (read only) and `--test-notification` is run once for the user to confirm.
