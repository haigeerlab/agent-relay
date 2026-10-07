# Spec: cleanup-gaps

## Objective

Close three gaps found on 2026-10-08 while the user and the coordinator ("第二轮联调") cleaned up 0.2.0's test leftovers
on the real host. None blocked 0.2.0; the user scheduled them for the next version (number decided at release).

1. An expired message blocks retiring an identity, and nothing shows which message.
2. A Codex delegation whose thread never got a turn cannot be closed: cancel answers `unknown` forever.
3. `bridge_register` (including `takeover`) silently brings a retired name back.

Readers: the user; the coordinator, who runs the real-host check after merge (gap 2 on the two real records).

## What exists today (measured, main 5d12346, 2026-10-08)

**Gap 1.** `hooks/native_collaboration_retire.py` `identity_state` counts every delivered message without an
acknowledgement, whatever its `delivery_state`. The bridge's own unread rule (`bridge/src/bridge-store.ts`
`UNREAD_FOR`) excludes `delivery_state = 'expired'`, so `bridge_inbox` and `bridge_register`'s `unread` show 0 while
retire refuses with "still has N unacknowledged message(s)" and names no message. Seen with message 125 (D13 test,
`expired`) on `ar-acc-round2-design-claude-wt`; the coordinator found its id only by reading the database.

**Gap 2.** `hooks/session_delegation_codex.py`:
- `create`: `thread/start` returns a thread id; if the permission check or `_catalog` then fails,
  `record_host_unknown(id, candidate)` stores `host_ref` with `state = unknown`, **no** `host_session_ref` and **no**
  `last_turn_ref`. No `turn/start` was ever sent.
- `status`: `thread/read` on that id raises `RpcRejected` → "app-server-request-rejected: -32600".
- `cancel`: `host_ref` is set, state is not `running`, so it calls `thread/archive`; `RpcRejected` → returns `unknown`
  with `prerequisite = host-request-rejected` and the row stays `unknown`.

The two real records match exactly: `r2-cx-review` e168eaf1… and 26977000…, `target_host = codex`, `state = unknown`,
`host_ref` set, `host_session_ref` NULL, `last_turn_ref` NULL (read-only query, 2026-10-08). The store already allows
`unknown → cancelled` with evidence `host-cancelled`.

**Gap 3.** `bridge/src/server.ts` `bridge_register` checks owner and binding conflicts (`takeover`) but not retirement;
`bridge-store.ts` `register` always sets `retired_at = NULL`. The tool description and
`docs/collaboration-interface.md` say "Registering again reactivates a retired agent". On 2026-10-08 my takeover
reactivated the identity the coordinator had just retired, with no word in the result.

The vendored bridge is already changed by five modules (delivery-state-machine, durable-ordering, idempotency, identity-check, ops-commands); `bridge/UPSTREAM.md` § "agent-relay changes" records each
change and `UPSTREAM.sha256` is rewritten in the same commit (`scripts/bridge-manifest.py`); the installer refuses a
copy that differs from the manifest.

## Assumptions

Confirmed by the user on 2026-10-08.

1. **Gap 1:** retire uses the bridge's unread rule: an `expired` message no longer blocks. Messages that still block
   (any other state) are listed in the refusal by id and delivery state (at most 10 ids, then "and N more"), never
   their bodies.
2. **Gap 2:** cancel closes a Codex record locally as `cancelled` only when all hold: `state = unknown`,
   `host_session_ref` NULL, `last_turn_ref` NULL (no turn was ever sent, so no work can have run), and the host
   rejects the request (`RpcRejected`). The result says why (`prerequisite = host-thread-absent`). Every other
   `unknown` (a turn was sent, the host's reply was uncertain, or a Claude target) is unchanged.
3. **Gap 3:** registering a retired name is refused unless the call passes `reactivate: true`, with or without
   `takeover`. The refusal names the name's retired state and says to pass `reactivate: true` only after the user
   agrees. With it, the name is restored and the result carries `reactivated: true` and a note with the earlier
   `retiredAt`. An active name behaves as today.
4. The bridge build in the installed runtime changes, so 0.2.x users get gap 3's fix through
   `native_collaboration_runtime.py upgrade --confirm` (sessions closed), as for earlier bridge changes; the CHANGELOG
   says so.
5. Release number is not decided here (the coordinator suggests 0.2.1).

## Decisions

- **D59 retire follows the bridge's unread rule and names what blocks (gap 1).** As assumption 1. Accepted on 2026-10-08.
- **D60 a never-turned Codex thread that the host rejects is closed locally (gap 2).** As assumption 2. Accepted on 2026-10-08.
- **D61 where gap 3 is fixed: A, chosen by the user on 2026-10-08.**
  - **A (recommended): change the vendored bridge.** `server.ts` `bridge_register` gains `reactivate` and the check;
    record the change in `UPSTREAM.md` and rewrite `UPSTREAM.sha256` in the same commit, as the five earlier modules
    did. Cost of later upstream syncs: one more small hunk in `server.ts`, a file that already carries agent-relay
    changes, so a sync re-applies it together with the others listed in `UPSTREAM.md`.
  - **B: leave the bridge alone and stop it in agent-relay's own layer.** There is no agent-relay layer between a
    host and `bridge_register` today: both hosts call the bridge's MCP tool directly. B needs either a proxy MCP
    server in front of the bridge (new component, every tool call passes through it) or a Claude PreToolUse hook
    (Claude only; Codex has no equivalent, so a Codex session could still reactivate). Upstream syncs cost nothing,
    but B covers only part of the problem or adds a component larger than the fix.

## Requirements

1. Gap 1 tests: identity with one `expired` unacknowledged message → retired; with one `accepted` unacknowledged
   message → refused, the message id and `accepted` in the diagnostic; 12 blocking messages → 10 ids and "and 2 more";
   no body text in any output.
2. Gap 2 tests (fake Codex app-server returning -32600): the never-turned record → `cancelled`, row `cancelled`,
   `prerequisite = host-thread-absent`; a record with a `last_turn_ref` and the same rejection → still `unknown`,
   unchanged; a `creating` record and a completed one behave as today.
3. Gap 3 tests (bridge, `node --test`): retire then register → refused, row still retired; retire then
   `takeover: true` → refused; `reactivate: true` → active, `reactivated: true`, note names the earlier `retiredAt`;
   an active name with `reactivate: true` → normal registration, no `reactivated`.
4. Docs: `bridge_register` tool description, `docs/collaboration-interface.md`, the `bridge retire` CLI message,
   `UPSTREAM.md` (A), CHANGELOG `Unreleased`.
5. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; bridge tests green.
6. Live check in a temporary `AGENT_RELAY_HOME`/HOME: gaps 1 and 3 end to end with the built runtime; gap 2 with the
   fake app-server only. The two real records are the coordinator's check after merge.

## Boundaries

- Always: never print message bodies; never close an `unknown` row that may have run work.
- Ask first: anything on the real `~/.agent-relay`, `~/.claude`, `~/.codex`.
- Never: push without approval; edit `~/.codex/config.toml`.

## Success criteria

Tests above green; live check passes; after merge the coordinator cancels e168ea and 269770 to `cancelled`, retires
an identity with only an expired message, and sees a register of a retired name refused.

## Open questions

None.
