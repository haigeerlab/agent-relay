# Plan: post-090-bridge

<!-- spec-guard: review approved -->

Based on [`spec/post-090-bridge.md`](../../spec/post-090-bridge.md) (approved by the user on 2026-10-24: assumptions
1–7, D251–D255). Built on branch `claude/unruffled-stonebraker-c923dd` together with `post-090-docs`; one PR for both
modules. Nothing here touches the main clone, the hosts or the runtime on this Mac.

Found while planning (read-only, 2026-10-24, main 538c6c3):
- `checkRecipient` (`src/addressing.ts:74`) reads the host as `store.getAgent(to)?.host ?? target`; the stale warning is
  the `if (!target)` block at line 124. The script warning goes next to the presence branches and that block skips a
  script host.
- The CLI `send` prints `sendMessage`'s object (`src/send.ts`), so a warning added in `checkRecipient` reaches both
  `bridge_send` and the CLI without extra code.
- `VERSION` is read by `cli-main.ts:206` (`--version`) and `server.ts:120` (`serverInfo`); the CLI help line is
  `cli-main.ts:32`. `cli.test.ts:153` keeps `VERSION` equal to `package.json`.
- Both duplicate returns in `deliver()` (`src/bridge-store.ts`, the idempotency-key one and D35's lenient loop) build
  `skipped: []`; `closedState(id)` already gives `{id, reason, by?}` or null.

## Task List

### Gate 0 (gate): ecosystem-lead on interface 2.9
Implementation starts only after the owner session relays ecosystem-lead's answer (Spec assumption 7). If the answer
changes the version decision, the Spec is revised and reviewed again first.

### Task 1: script recipient warning (D251; requirements 1)
Red first: in `script-access.test.ts` (store-level `sendMessage`/`checkRecipient`), a send to a script identity carries
the script warning and no "no background ping binding" warning even when its last activity is older than a day; a send
to a Claude and to a Codex identity carries no script warning. In `script-cli.test.ts`, CLI `send` from one script
identity to another prints the warning in its JSON. Green: one branch in `checkRecipient`; the stale block skips a
script host. Verification: the new tests and the existing addressing / script tests pass.

### Task 2: version follows runtime releases (D252; requirement 2)
Red first in `cli.test.ts`: `VERSION` equals `package.json` and `package-lock.json` (both version fields) and is not
higher than the `version` in `../.claude-plugin/plugin.json` and `../.codex-plugin/plugin.json`; the help text says
`--version` prints the agent-relay release the runtime was built from. Green: the help line and the lock-file check.
The number itself moves to `0.9.3` in the **release PR**, together with `plugin.json` (in this branch the plugin is
still 0.9.2, so a bridge at 0.9.3 would fail the "not higher" test). `RELEASING.md` gets the rule: a release that
changes runtime files sets `version.ts`, `package.json` and `package-lock.json` to the release's version and runs
`scripts/bridge-manifest.py`; a hooks- or docs-only release leaves them alone.

### Task 3: duplicate returns report skipped ids (D253; requirement 3)
Red first in `request-closing.test.ts`: (a) a reply with `alsoAnswers: [a, b]` that closed only `a` (b was open, then
closed by another message), retried — lenient fold — returns `skipped: [{id: b, reason: "answered", by}]`; (b) the same
with `withdraws` and reason `withdrawn`; (c) an idempotency-key retry after another message closed one of its ids lists
it; (d) an exact retry with nothing closed elsewhere returns `skipped: []`; (e) a duplicate send without either list has
no `skipped` field in `bridge_send` (unchanged). Green: a helper `skippedOnRetry(alsoAnswers, withdraws, storedId)` used
by both duplicate returns. `spec/request-closing.md` gets a dated revision line under D238 pointing to D253.

### Task 4: readable error for a missing closure row (D254; requirement 4)
Red first in `request-closing.test.ts`: a store whose closure insert raises a constraint error with no row for that
request (fixture: a trigger on `request_closures` that raises `constraint failed`) makes `deliver` throw an `Error`
naming the request id, the message id and the original message, not a `TypeError`. Green: the check in
`closeRequests`.

### Task 5: interface 2.9 and docs (D255; requirement 5)
`interface.json` `"interface": "2.9"`; `docs/collaboration-interface.md` §1 (0.9.3 implements 2.9) and the `bridge_send`
row (script warning, `skipped` on a retry); the interface-version guards in `test_packaging.py` / skill tests updated
where they pin 2.8; skills `collab` and `session-routing` only if they say `skipped` is empty on a retry; `UPSTREAM.md`
rows; `python3 scripts/bridge-manifest.py`; `RELEASING.md` bridge-version rule (from Task 2); CHANGELOG `[Unreleased]`
(interface 2.9, runtime upgrade needed).

### Checkpoint (report): bridge green
`npm run check` in `bridge/` green; results recorded in the todo; continue with `post-090-docs`.

### Checkpoint (gate): module review
After both modules are built: local validation, PR and CI are tracked in `post-090-docs`' todo (one PR). The owner
session reviews; the user merges. The release PR (0.9.3, bridge and plugin versions), the tag and the upgrade on this
Mac are separate steps the owner session asks of the user.

## Risks

- Task 2's version timing: setting the bridge to 0.9.3 before `plugin.json` is 0.9.3 would make the new test fail and a
  CI run of this branch would show a version not yet released; hence the bump goes into the release PR.
- Task 3 changes what a retry returns; consumers that compared `skipped` to `[]` on a retry would see entries. The
  interface bump (2.9) and the CHANGELOG say so.
