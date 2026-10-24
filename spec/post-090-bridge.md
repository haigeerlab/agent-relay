# Spec: post-090-bridge

<!-- spec-guard: review approved d23b98f9c201 -->

## Objective

The bridge half of ledger item AJM8B1H ("follow-up fixes after the freeze"): small fixes and review suggestions that
collected after 0.9.0 and change the bridge's runtime files. Requested by the user in the owner session ("可以", then
"开始"); assumptions confirmed by the user in this session on 2026-10-24. Released together with `post-090-docs` as
**0.9.3** (interface 2.9, schema 7); because the runtime files change, the release needs `upgrade --confirm`.

Readers: the user; the owner session (review, release, acceptance).

## What exists today (main 538c6c3, v0.9.2)

- `bridge/src/addressing.ts` `checkRecipient` collects `bridge_send`'s recipient warnings (stopped, not-loaded,
  waiting-approval, failed pings, "no background ping binding and was last active …"). A recorded host `script`
  (script-access D244) has presence `unknown` with detail "script identity" (`views.ts`), never has a wake binding, and
  gets no warning of its own; once the identity has been idle longer than `STALE_UNBOUND_MS` it gets the generic
  "Nothing will prompt it to read this". The CLI that a script uses has `agents`, `outbox`, `sessions`, `send` and no
  inbox command (D241–D243).
- `bridge/src/version.ts` `VERSION = "0.4.0"` (the upstream package version; `package.json` and `package-lock.json` say
  the same, a test keeps `VERSION` equal to `package.json`). It is printed by `agent-relay --version` and sent as the MCP
  `serverInfo.version`. `package.json` and `package-lock.json` are runtime files (`RUNTIME_FILES`, runtime-mark-scope
  D248), so changing them makes `status` report the runtime as not current.
- `bridge/src/bridge-store.ts` `deliver()`: both duplicate returns (idempotency key, and D35's reply fold with its exact
  then lenient match through `closableBy`) return `skipped: []` (D238). With the lenient match, an id of the retried
  list that another message has closed since is in neither `closed` nor `skipped`.
- `closeRequests()` catches a constraint error from the closure insert, reads the closure row and records the id as
  skipped. If the row is missing (the constraint was not the unique request id), `other` is `undefined` and the send
  fails with a `TypeError` that says nothing useful.

## Assumptions (confirmed by the user, 2026-10-24)

1. **Two modules, one release.** This module holds everything that changes bridge runtime files; `post-090-docs` holds
   hooks, bridge tests and docs. Both ship as 0.9.3 with one runtime upgrade and one acceptance.
2. **Script recipient warning.** When the recorded host of a direct recipient is `script`, `checkRecipient` adds one
   warning: it is a script identity, nothing wakes it or prompts it to read, and an answer comes only when its script
   next runs. The generic stale "no background ping binding" warning is not added for a script identity (the new one
   says more). The CLI `send` from one script identity to another shows the same warning. Warnings only: delivery,
   presence and `interface.json` unchanged (interface stays 2.8).
3. **Version follows runtime releases.** The bridge's version (`version.ts`, `package.json`, `package-lock.json`) is set
   to the agent-relay release that last changed runtime files; this release sets it to `0.9.3`. `--version` and
   `serverInfo.version` therefore say which release the runtime was built from. A hooks- or docs-only release leaves it
   unchanged, so it does not force a runtime upgrade. A test keeps it no higher than `plugin.json`'s version (both
   manifests); `RELEASING.md` gains the rule. `UPSTREAM.md` records that the upstream package version was 0.4.0.
4. **D238 changes: a lenient fold reports what it skipped.** On either duplicate return, when the send gave
   `alsoAnswers` or `withdraws`, `skipped` lists every id of those lists that the stored message did not close and that
   is closed now (withdrawn, answered by another message, failed or expired), with the same `{id, reason, by?}` shape as
   a first send, sorted by id; still `[]` when there are none. Nothing is stored for it. The idempotency comparison and
   D35's matching are unchanged. This is an interface change, see assumption 7.
5. **Readable error for a missing closure row.** If the closure insert fails with a constraint error and no closure row
   exists for that request, `closeRequests` throws an `Error` naming the request and message ids and the database's own
   message; the send is refused as any other storage error is.
6. **Out of scope.** Mailbox schema (stays 7), delivery and wake behaviour, the host and the runtime on this Mac.
7. **Interface 2.9 (revised 2026-10-24 after the owner session asked; supersedes "interface stays 2.8" in
   assumptions 2 and 4).** Judged by `docs/collaboration-interface.md` §1 (removing or renaming a tool, field, state or
   command, or narrowing an accepted input, is major; additions are minor):
   - D253 changes documented behaviour: the `bridge_send` row says `skipped` is "`[]` on a duplicate retry". It removes
     nothing, renames nothing and refuses nothing that was accepted; `skipped` keeps its shape and its meaning ("already
     closed elsewhere, nothing to redo"), and a reader that ignored it on a retry loses nothing. It adds entries a
     consumer can see, so it is an addition: **minor, 2.8 → 2.9** (as 2.7 counted the skip widening as minor).
     `interface.json` `"interface": "2.9"`; §1 and the `bridge_send` row are updated. Spec Guard's range `>= 1.0, < 3.0`
     still holds.
   - D251 adds a warning. `warnings` is free text that already grows without a version (acceptance-030-gaps D72), so it
     is no interface change.
   - D252 changes `--version` and the MCP `serverInfo.version`. Neither is in the interface document or
     `interface.json` (§2.4 lists the script commands `agents`, `outbox`, `sessions`, `send`), so it is no interface
     change.
   - Because the interface version changes, ecosystem-lead is asked (through the owner session) after this Spec is
     approved and before implementation; implementation waits for its answer.

## Decisions

- **D251 a script recipient is named in the send warnings.** Assumption 2.
- **D252 the bridge version is the last runtime release.** Assumption 3. The CLI help line says so.
- **D253 duplicate returns report skipped ids (revises D238).** Assumption 4. D238's "a duplicate retry returns
  `skipped: []`" becomes "a duplicate retry returns the ids of its lists that are closed elsewhere"; `spec/request-closing.md`
  gets a dated revision note pointing here.
- **D254 a lost race without a closure row is a readable error.** Assumption 5.
- **D255 interface 2.9.** Assumption 7; only D253 counts.

## Requirements

1. Red first (`addressing` or `script-cli` tests): a send to a script identity carries the script warning and not the
   stale one; a send to a Claude or Codex identity carries no script warning; the CLI `send` to a script identity
   prints it.
2. Red first (`cli.test.ts`): `VERSION` equals `package.json` (existing) and is not higher than the version in
   `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`; `--version` prints `VERSION`.
3. Red first (`request-closing.test.ts`): a retry folded by the lenient match after another message closed one of its
   ids returns that id in `skipped` with reason and `by`; an exact retry with nothing closed elsewhere returns
   `skipped: []`; the same for an idempotency-key retry.
4. Red first: a closure insert that hits a constraint without a closure row raises the readable error (test through a
   store whose closure table has an extra constraint, or an equivalent fixture).
5. `UPSTREAM.md` rows for every changed bridge file; `python3 scripts/bridge-manifest.py`; `interface.json` 2.9 and
   interface document §1 and `bridge_send` row (D251, D253, D255); skills `collab` and `session-routing` only if their wording of `skipped` on a
   retry needs it; CHANGELOG `[Unreleased]`.
6. `scripts/validate.sh` green on Python 3.9, 3.10, 3.14; CI green.

## Boundaries

- Ask first: anything on this Mac's runtime or hosts (none planned; acceptance after release is the owner session's).
- Wait: implementation starts only after ecosystem-lead has answered on interface 2.9 (assumption 7).
- Never: a schema change; a new delivery or wake state; changing what is refused.

## Acceptance (owner session, after release)

- After `upgrade --confirm`, `~/.agent-relay/bin/agent-relay --version` prints 0.9.3.
- A session's `bridge_send` to a script identity carries the script warning.

## Open questions

None.
