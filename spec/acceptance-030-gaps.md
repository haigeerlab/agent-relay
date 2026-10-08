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
