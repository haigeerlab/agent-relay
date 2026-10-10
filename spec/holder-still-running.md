# Spec: holder-still-running

## Objective

Third module of 0.6.2 (bridge). From the round-2 coordinator's review of #74 and #77 (2026-10-10): `bridge_register` with
`takeover: true` moves a name away from any session, running or not. 0.6.2's resumed delegation uses takeover for its own
stopped session, and only the envelope's wording limits it to a holder that is "no longer running". The bridge itself
must refuse to take a name from a Claude session that is still running, so a bypassed prompt cannot do it.

Readers: the user; the round-2 coordinator (reviews the spec, re-checks after release).

## What exists today (main cec6d31)

`bridge/src/server.ts` `bridge_register`: with an owner or wake-binding conflict and no `takeover`, the call is refused,
and for a Claude holder the message says "(still running)" or "(no longer running)" from `isClaudeSessionLive` (which
counts non-macOS as live so that message is not wrong). With `takeover: true` every conflict passes, a note "was taken
over from another session" is added, and since D186 a new wake replaces the old binding. `claudeSessionsOrNull` returns
the live sessions, or `null` when the registry cannot be read here (off macOS, or a directory this process may not list).

## Assumptions (accepted by the user 2026-10-10)

1. **Refuse a live Claude holder.** With `takeover: true`, when a conflicting holder — the registered owner, or the
   session the name's wake is bound to — is a Claude session that the readable registry lists as running, the call is
   refused; nothing changes (owner, binding, pending wake jobs). The message starts with `holder-still-running:`, names
   the agent and says the next step: stop that session first, or choose a different name.
2. **Readable registry, holder not in it:** takeover proceeds as today.
3. **Registry not readable (including off macOS):** takeover proceeds, and the result's notes say the bridge could not
   confirm whether the previous Claude session is still running — never that it stopped.
4. **Codex holder:** takeover proceeds as today, and the notes say the bridge cannot confirm whether the previous Codex
   session is still running (the coordinator, 2026-10-10).
5. **`reactivate` + `takeover`** follows the same rule. The refusal without `takeover` and its message are unchanged.
6. **0.6.2 delegation unaffected:** the resumed turn takes over its own stopped session (`takeover: true, wake: null`,
   then `wake: "auto"`); a test covers that sequence against a stopped holder.
7. This tightens today's behaviour: taking a name from a Claude session that is still open now needs that session
   stopped first. The tool description of `takeover` says so. Interface stays 2.0, mailbox schema 5.
8. Vendored-bridge change: `UPSTREAM.md` row and `python3 -B scripts/bridge-manifest.py` in the same commit (D24);
   CHANGELOG `[Unreleased]` says it takes effect after `upgrade --confirm`. collab skill: one sentence that takeover of a
   running session's name is refused.

## Decisions

- **D187 takeover never takes a name from a running Claude session.** Assumptions 1–7.

## Requirements

1. Red first (`bridge/test/identity.test.ts`, real stdio sessions, a registry fixture as the presence tests build it):
   owner conflict with a live holder → refused with `holder-still-running`, owner and binding unchanged, a pending wake
   job still pending; binding-only conflict with a live bound session → refused; holder not in a readable registry →
   taken over, no "could not confirm" note; unreadable registry → taken over with the note; Codex holder → taken over
   with the Codex note; `reactivate` + `takeover` against a live holder → refused; the delegation sequence
   (takeover + `wake: null`, then `wake: "auto"`) against a stopped holder → both succeed.
2. Existing identity, takeover and D186 tests stay green unchanged.
3. `UPSTREAM.md`, manifest, CHANGELOG, collab sentence (skill guard test).
4. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 with Node 24 first on PATH; bridge `npm run check`; CI green.

## Boundaries

- Never: stop or signal the holder's session; guess liveness from names, titles or recent activity.
- Ask first: nothing in this module changes the user's machine; the runtime upgrade happens with the 0.6.2 release.

## Acceptance (coordinator, after 0.6.2)

- A second Claude session's `takeover` of a name held by an open session is refused with `holder-still-running`; after
  that session is closed it succeeds.
- Codex → Claude Code create → stop → continue still reports back (the delegation's own takeover).

## Open questions

None. Accepted by the user on 2026-10-10; spec review by the round-2 coordinator pending.
