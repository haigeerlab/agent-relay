# Spec: takeover-wake-rebind

## Objective

Found on 2026-10-10 in a real check: a resumed Claude delegation re-registered its own name with
`bridge_register({agent, takeover: true, wake: "auto"})` and was refused with "Agent is already bound to another
session. Use a unique agent name, or unbind it with wake: null first." The tool description says `takeover` moves "a
name registered by or bound to another session", so `takeover` with a new `wake` must replace the binding. 0.6.2 works
around it in the delegation envelope (takeover with `wake: null`, then `wake: "auto"`).

Readers: the user; the coordinator, who re-checks on the real host after release.

## What exists today (measured, main 6497f41, 2026-10-10)

`bridge/src/server.ts` `bridge_register`:
1. `bindingConflict` = a new wake target differs from the current one; with an owner or binding conflict and no
   `takeover` the call is refused (identity-check).
2. With `takeover: true` that check passes, a note "was taken over from another session" is added, then
   `store.wakes.bind(agent, target)` runs.
3. `bridge/src/wake-queue.ts` `WakeQueue.bind` refuses any change from one target to another and throws the message
   above, so step 2 never completes. `bind(agent, null)` deletes the binding and cancels the agent's `pending` wake
   jobs ("Recipient unbound").
4. Other caller of `bind`: `bridge-store.ts` retire, with `null` only.

## Assumptions

Confirmed by the user on 2026-10-10.

1. `takeover: true` with a new wake (`"auto"` or `{app, sessionId}`) on a name bound to another session replaces the
   binding in one transaction, with the same effect as `wake: null` followed by the new wake: the old binding's
   `pending` wake jobs are cancelled; messages stay unread in the inbox; the result still gives `unread`, the
   bridge_inbox hint and the "taken over" note. Pending jobs are not moved to the new session.
2. Everything else is unchanged: the refusal without `takeover`; `wake: null`; omitted `wake`; re-registering from the
   same session; `WakeQueue.bind` keeps its own conflict check and replaces only when the caller asks. Interface stays
   2.0, mailbox schema 5, the tool description is unchanged.
3. Vendored-bridge change: `UPSTREAM.md` row and `python3 -B scripts/bridge-manifest.py` in the same commit (D24);
   CHANGELOG `[Unreleased]` says it takes effect after `upgrade --confirm`.
4. The 0.6.2 envelope workaround stays (older runtimes need it); removing it is out of scope.
5. Verification is the bridge tests (real stdio sessions) and `scripts/validate.sh`; no separate temporary-HOME live
   check. The coordinator re-checks on the real host after release.
6. Release number is decided at release.

## Decisions

- **D186 takeover replaces a wake binding.** Assumptions 1–2. Accepted on 2026-10-10.

## Requirements

1. Bridge tests in `test/identity.test.ts`, red first:
   - A registers a name with `wake: "auto"` and has a pending wake job (a message sent to it); B registers it with
     `takeover: true, wake: "auto"` → ok, `wake` is B's session, the note says taken over, A's pending job is
     `cancelled`, the message is still unread for the name.
   - The same with an explicit `wake: {app: "claude", sessionId: <B>}`.
   - B without `takeover` → refused as before; A's binding unchanged.
   - B with `takeover: true` and no `wake` → binding unchanged (still A's).
   - A registering again with `wake: "auto"` → ok, binding unchanged.
2. `server.ts` asks `WakeQueue.bind` to replace only when `takeover` resolved a binding conflict; `bind` does the
   delete, cancel and insert in one transaction.
3. `UPSTREAM.md` row, manifest, CHANGELOG `[Unreleased]` with the runtime upgrade note.
4. `scripts/validate.sh` green with Node 24 on PATH; bridge `npm run check` green.

## Boundaries

- Always: no behaviour change outside the takeover path.
- Ask first: the real `~/.agent-relay`, `~/.claude`, `~/.codex`.
- Never: push or merge without approval.

## Success criteria

Tests and validate pass; after release the resumed-delegation re-registration with `takeover: true, wake: "auto"`
succeeds on the real host.

## Open questions

None.
