# Spec: codex-not-loaded

## Objective

Only module of 0.6.11 (bridge). From a report relayed on 2026-10-16 by a Codex monitoring session (mailbox name
`spec-guard-monitor`), with the user's consent, and the user's decisions the same day ("可以，按你的建议排，先做第 1 块的复现";
"已合并，按调整后的方案做 0.6.11"; "确认，六条假设通过，第 2 块不做"): after the ChatGPT app restarts, or a Codex task sits
idle for long, pings to that task retry as `offline` with the detail "Codex local connection unavailable" until the user
opens the task. The sentence points at the wrong cause, and the user was never told which task to open.

## What exists today (main 51ea37b, v0.6.10)

- `bridge/src/codex-wake.ts` asks the app `thread-owner-discovery` before every ping. Any `IpcError` before the turn is
  submitted (cannot connect, connect timeout, no response in 10 s, response lost) becomes `pending`/`offline` with
  "Codex local connection unavailable".
- `bridge/src/presence.ts` `codexOwner` returns `null` for the same errors, shown as `presence: unknown` ("the Codex
  app cannot be asked").
- Measured 2026-10-16 (read-only probe, the same request): three loaded tasks answered in 5–18 ms; a task the user had
  not opened since the app restarted, and a thread id that does not exist, got **no answer** and timed out after 10 s.
  Messages #2927 and #2929 retried 29 and 24 times this way and were read within a minute of the user opening the tasks.
- The Codex offline notice (D67) says "Codex is not running; the message waits" and names the agent in its subtitle.
- Identity: a Codex task's bridge process carries no session id in its environment (checked on all six running
  ChatGPT-started bridges), so the bridge cannot tell which Codex task calls it; a name is proven per process, and a new
  process (app restart, task reload) needs `bridge_register` with the same name again. Codex tasks already do this
  themselves within seconds.

## Assumptions (accepted by the user 2026-10-16)

1. A discovery request that gets no answer in time (before anything was submitted) means the task is not loaded in the
   app: the ping stays `pending`/`offline` with the detail "This Codex task is not loaded in the ChatGPT app (it was not
   opened since the app started or it was idle); open it there and the message is delivered". A socket that cannot be
   reached at all keeps "Codex local connection unavailable". Retry rules are unchanged.
2. `presence` gains the value `not-loaded` for such a task (`stopped` stays for "the app answered: no owner",
   `unknown` for "the app cannot be reached").
3. The Codex offline notice for such a ping says to open that task in the ChatGPT app (its mailbox name is already in
   the notice).
4. Docs and skills say the bridge cannot tell which Codex task calls it; after the identity is lost the task registers
   again with the same name (no takeover). Auto-recovery by session id is not built: the only id available is the one
   the task itself reports, which proves nothing.
5. Release: bridge change, 0.6.11, `upgrade --confirm`; interface 2.0 (one more `presence` value), schema 5 unchanged.
6. Process as usual; the round-2 coordinator reviews the PRs.

## Decisions

- **D200 a Codex task the app does not answer for is reported as not loaded, with what to do; identity recovery stays
  a re-registration because the bridge cannot verify a Codex caller.**

## Requirements

1. Red first, `bridge/test/`: with a fake Codex IPC socket that accepts and never answers discovery, the wake result is
   `pending`/`offline` with the not-loaded detail; a missing socket keeps the old detail; an answer "no owner" keeps
   "Codex task has no connected owner"; a timeout after the turn was submitted stays `unknown`.
2. Red first: `codexOwner`/`codexPresence` give `not-loaded` for the silent socket, `unknown` for a missing one,
   `stopped`/`running` as before; `bridge_agents` shows it.
3. Red first: the Codex notice for a not-loaded ping tells the user to open the task in the ChatGPT app.
4. `docs/BACKGROUND-WAKE.md`, `skills/collab` (identity after a restart), `docs/collaboration-interface.md` (presence
   values), CHANGELOG, `UPSTREAM.md` and manifest (D24).
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; CI green.

## Boundaries

- Never: treat a self-reported thread id as proof of identity; read Codex private state; change retry windows.

## Acceptance (coordinator, after 0.6.11)

- After restarting the ChatGPT app, a ping to a task not yet opened shows the not-loaded detail and `presence:
  not-loaded`; opening the task delivers it.
