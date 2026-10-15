# Spec: upgrade-codex-restart-check

## Objective

Second module of 0.6.9 (hooks only; no bridge change). Same report and decision as `codex-request-via-mailbox`
(assumption 5): after a runtime upgrade, every Codex task that was already running loses its mailbox connection
("Transport closed") and Codex does not reconnect until the ChatGPT desktop app is fully quit and opened again. Today
only the CHANGELOG says so; nothing checks it.

## What exists today (main 33936e0, v0.6.8)

- `upgrade-restart-note` documents the restart in the CHANGELOG, README and the collaboration-ops
  skill; `upgrade --confirm` prints `state`, `bridge`, `counts`, `previous`, `backup`, `rollback`, and no restart hint.
- Each upgrade keeps the old runtime as `~/.agent-relay/runtime.previous-<UTC stamp>` (`YYYYMMDDTHHMMSSZ`).
- `doctor` (`hooks/native_collaboration_doctor.py`) has no check of the Codex app.
- Measured 2026-10-15: the ChatGPT app process (`/Applications/ChatGPT.app/Contents/MacOS/ChatGPT`) started 17:39,
  the upgrade ran 18:04:55; no bridge came back until the app was restarted at 18:07:26 (a new bridge at 18:07:35).
  On 10-15 16:24 the same happened after the 0.6.7 upgrade and the user had to quit and reopen Codex.

## Assumptions (accepted by the user 2026-10-16, assumption 5 of the 0.6.9 list)

1. `upgrade --confirm` adds a `next` sentence to its output when it upgraded: quit the ChatGPT desktop app completely
   (⌘Q) and open it again; open new Claude Code sessions.
2. `doctor` adds a check `codex-restart`: if a ChatGPT app process started before the newest runtime upgrade, `warn`
   with that sentence; otherwise `ok`; no ChatGPT process, or no upgrade on record → `ok` saying so. Read only.
3. The upgrade time is the newest `runtime.previous-<stamp>`; the process start comes from `ps -o lstart=` for the exact
   app executable path. Nothing else is read; Codex private state is not touched. The stamp is UTC and `lstart` is
   local time: both become absolute times before they are compared (`ps` runs with `TZ=UTC`, as the Claude adapter
   already does, or the local zone is applied; round-2 review of #104).
4. Release with `codex-request-via-mailbox` as 0.6.9; no `upgrade --confirm` needed.

## Decisions

- **D196 after a runtime upgrade the user is told to restart the Codex app, and doctor warns while the app still runs
  from before the upgrade.** Assumptions 1–3.

## Requirements

1. Red first, `hooks/test_runtime_upgrade.py`: an upgraded result carries `next` with the restart sentence; `current`
   carries none.
2. Red first, `hooks/test_doctor.py` (injected clock, process list and runtime root): app started before the newest
   upgrade → `warn`; after → `ok`; no app process → `ok`; no `runtime.previous-*` → `ok`; an unparsable stamp or
   `ps` failure → `ok` with "cannot tell", never `fail`. A cross-zone case: on a +08:00 Mac the app started a few
   hours before the upgrade in local clock terms but after it in absolute time (and the reverse) is judged by absolute
   time.
3. README "升级运行时" and CHANGELOG `[Unreleased]` mention the new output and check.
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; CI green.

## Boundaries

- Never: restart, quit or signal the ChatGPT app; read Codex private state.
- Not built: a `codex` CLI session in a terminal loses its connection after an upgrade too; doctor does not see it
  (round-2 review of #104). Only the desktop app is checked.

## Acceptance (coordinator, after 0.6.9)

- Right after the next runtime upgrade, `doctor` shows `codex-restart` as `warn`; after the user restarts the app it
  shows `ok`.
