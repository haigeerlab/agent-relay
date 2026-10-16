# Spec: waiting-list-all-hosts

## Objective

Second module of 0.6.10 (bridge). Item 7 of the same list: an upper-layer plugin, running as a Claude session, will
wake stopped Claude sessions itself (the desktop app's session message tool can start a stopped session; measured by
the reporting session). It needs a stable, machine-readable list of joined identities that have unhandled messages,
with their presence, how many messages and since when.

## What exists today (main 7a2af10, v0.6.9)

- `bridge_agents` lists each agent with `unread`, `lastActivity`, `presence` (`running`, `stopped`, `unknown`, …),
  `wake` and `lastPing`; only agents whose recorded host is Codex carry `waiting: {count, from, ids}`
  (`BridgeStore.codexWaiting`, D77).
- No field gives the time of the oldest waiting message, and no document promises these fields stay.

## Assumptions (accepted by the user 2026-10-16)

1. `waiting` is given for every agent with unhandled direct messages, whatever its host: `count`, `from` (distinct
   senders), `ids` (at most 20, oldest first), and new `oldestAt` (ISO time of the oldest one). Failed and expired
   messages are left out, as today.
2. `bridge_agents` stays the interface (no new CLI): together with `presence` and `wake` it answers "stopped and has
   messages waiting". `docs/collaboration-interface.md` lists these fields and promises that within interface 2.x they
   are only added to, never renamed or removed.
3. The tool description no longer says "Codex" only; it still says no bodies are returned.
4. Release with the other two modules as 0.6.10; interface 2.0, schema 5 unchanged.

## Decisions

- **D198 every joined identity with unhandled messages shows them in `bridge_agents.waiting`, with `oldestAt`; the
  fields are a documented, add-only part of interface 2.x.**

## Requirements

1. Red first: a Claude-hosted agent and an agent with no recorded host both carry `waiting` with the right count,
   senders, ids and `oldestAt`; acknowledged, failed and expired messages are not counted; no `waiting` when nothing
   waits; no body anywhere.
2. `docs/collaboration-interface.md` row; `bridge_agents` description; CHANGELOG; `UPSTREAM.md` and manifest (D24).
3. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Never: return message bodies; read a session's private state to fill these fields.

## Acceptance (coordinator, after 0.6.10)

- On the real mailbox, a stopped Claude session with unhandled messages shows `presence.state: "stopped"` and
  `waiting` with the right `oldestAt`.
