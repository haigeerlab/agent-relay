# Spec: register-retired-hint

## Objective

Observation O1 from the 0.2.1 real-host acceptance (`docs/acceptance/2026-10-08-cleanup-gaps.md`): a session that does
not own a retired name and calls `bridge_register` with `reactivate: true` is refused only for ownership, so it never
learns the name is retired. The test session took the name to be active. Make that refusal say so.

Readers: the user; the coordinator ("第二轮联调"), who found O1.

## What exists today (measured, main 79b8f23, 2026-10-08)

`bridge/src/server.ts` `bridge_register` (cleanup-gaps D61):
1. `existing?.retiredAt && !reactivate` → "\"<name>\" was retired at <time> by <who>. Ask the user: …reactivate: true…".
2. With `reactivate: true` that check passes; then an owner or binding conflict without `takeover` throws
   "\"<name>\" is registered by another <app> session (…). … pass takeover: true only after the user agrees …" —
   nothing about retirement.
3. `reactivate: true` with `takeover: true` restores the name (`reactivated: true`).

## Assumptions

Confirmed by the user on 2026-10-08.

1. Only the conflict refusal in step 2 changes: when the row is retired it adds one sentence — "It was retired at
   <time> by <who>; bringing it back here needs reactivate: true together with takeover: true, only after the user
   agrees." When the row is active the text is unchanged.
2. No behaviour change: the same calls are refused or accepted as in 0.2.1; interface stays 1.1.
3. It is a vendored-bridge change: `bridge/UPSTREAM.md` row, `UPSTREAM.sha256` regenerated; users get it through
   `upgrade --confirm`, as for 0.2.1.
4. Release number is decided at release.

## Decisions

- **D64 the ownership refusal names a retired state (O1).** As assumptions 1–2. Accepted on 2026-10-08.

## Requirements

1. Bridge test (`test/identity.test.ts`), red first: session A registers and retires a name; session B with
   `reactivate: true` → refused, text has the ownership part, "was retired at <time> by <who>" and
   "reactivate: true together with takeover: true"; the row stays retired. An active name owned by A, registered by B
   without `takeover` → refusal without "retired". `reactivate` + `takeover` from B → `reactivated: true` (unchanged).
2. `UPSTREAM.md` row and manifest; CHANGELOG `[Unreleased]` entry with the upgrade note.
3. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; bridge `npm run check` green.
4. Live check in a temporary `AGENT_RELAY_HOME`/HOME: runtime built from this checkout, two stdio sessions, the three
   cases above.

## Boundaries

- Always: no behaviour change beyond the message.
- Ask first: the real `~/.agent-relay`, `~/.claude`, `~/.codex`.
- Never: push without approval.

## Success criteria

Tests and live check pass; after release the coordinator sees the retired state in the refusal on the real host.

## Open questions

None.
