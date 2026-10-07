# Spec: bridge-vendoring

## Objective

Bring the pinned upstream bridge (`WebisityStudio/claude-codex-mcp-bridge` at `8f12c880cfdba73812b6ab7bc0f373fc467e0343`,
MIT) into the agent-relay repository and install the runtime from that copy instead of fetching upstream. Only the
source and install path change: the built runtime must be byte-identical to today's, so every installed user and
every existing test sees the same bridge. This corresponds to the phase 0 decision "maintain the pinned upstream
bridge inside agent-relay"; `delivery-state-machine`, `durable-ordering`, `idempotency` and `identity-check` then
change bridge code here.

Readers: the user; agents building the later bridge-changing modules; the round 2 operator.

## What exists today (measured, 2026-10-07, main 9b1b3fa)

- `install_runtime` (`native_collaboration_runtime.py`) stages a temp dir, `git fetch --depth 1` of the pinned commit
  from GitHub, checks `git rev-parse HEAD`, then `npm ci --ignore-scripts --no-audit --no-fund` and `npm run build`
  (`tsc` into `dist/`, source maps with relative paths), adds `mailbox/`, `data/`, `manifest.json`
  (`{"commit": "8f12c88…"}`), and renames the stage into place. `status()` requires that exact manifest.
- Upstream at that commit has 62 tracked files (520 KB): `src/` 26 and `test/` 13 (300 KB together), `package.json`,
  `package-lock.json`, `tsconfig*.json`, `scripts/` (build, two dev scripts, a demo-gif generator), `README.md`,
  `CHANGELOG.md`, `INSTRUCTIONS.md`, `LICENSE` (MIT, "Copyright (c) 2026 Tesla Major"), `docs/` 3, `assets/`
  (93 KB demo gif, logo), `skills/` 3 and `agents/` 1 (Claude Code worker skills/agent for `ask_codex` and
  `review_with_codex`), `.github/workflows/ci.yml`.
- Runtime dependencies (`@modelcontextprotocol/sdk`, `zod`) and dev ones (`typescript`, `tsx`, `@types/node`) come
  from the npm registry through `package-lock.json` integrity hashes.
- This Mac's installed runtime `~/.agent-relay/runtime` is a git checkout of that commit, so its object store can
  prove a copy is identical without network.

## Assumptions

Confirmed by the user on 2026-10-07, including the left-out list and the location.

1. **Location:** `plugins/agent-relay/bridge/`, inside the plugin, so a marketplace install carries it and the
   installer finds it next to `hooks/`.
2. **What is vendored:** everything needed to build, test and maintain the bridge — `src/`, `test/`,
   `scripts/build.mjs`, `scripts/mailbox-request.ts`, `scripts/smoke-orchestrator.ts`, `package.json`,
   `package-lock.json`, `tsconfig.json`, `tsconfig.test.json`, `.gitignore`, `LICENSE`, `README.md`, `CHANGELOG.md`,
   `INSTRUCTIONS.md`, `docs/`. **Left out:** `skills/` and `agents/` (worker features agent-relay denies; a host
   could otherwise pick them up from the plugin tree), `assets/` and `scripts/generate-demo-gif.py` (demo media),
   `.github/` (upstream CI). None of these is read by the build or the runtime. The README keeps its logo link
   broken rather than being edited.
3. **npm dependencies still come from the registry** through the unchanged `package-lock.json`; vendoring
   `node_modules` is out of scope. Install still needs network for `npm ci`, but no longer for `git`.
4. **Existing runtimes stay `ready`.** A runtime installed from GitHub keeps its manifest `{"commit": "8f12c88…"}`
   and is still accepted; only new installs get the version mark of D26. Nothing needs migrating in this module.
5. **No spec-guard change:** `interface.json`, the probe and the status output are unchanged.

## Decisions

D23–D25 accepted with the spec on 2026-10-07.

- **D23 provenance files.** `bridge/UPSTREAM.md` records repository, commit, date, licence, the left-out paths and
  "agent-relay changes: none" (later modules append theirs). `bridge/UPSTREAM.sha256` lists the SHA-256 of every
  vendored file.
- **D24 install verifies the copy.** `install_runtime` copies `bridge/` (without `node_modules`, `dist`) into the
  stage, checks every file against `UPSTREAM.sha256` and refuses on any extra, missing or changed file, then runs the
  same `npm ci` and build. This replaces the `git rev-parse` check; `git` is no longer needed. A module that changes
  the bridge later updates `UPSTREAM.sha256` and `UPSTREAM.md` in the same commit.
- **D25 identity proof (one-off, this module).** (a) every vendored file's git blob hash equals the blob at
  `8f12c88` in the local runtime's object store; (b) `dist/` built by the new installer is byte-identical to the
  current runtime's `dist/`, and the resolved npm dependency tree (`npm ls --all --json`) equals the current
  runtime's; (c) upstream's own `npm test` passes in a built copy, with the test count recorded; (d) `probe` is ready
  with the same 17 tools.

- **D26 version mark now, upgrade command later (user, 2026-10-07).** New installs write the manifest
  `{"commit": "8f12c88…", "source": "vendored", "tree": "<SHA-256 of UPSTREAM.sha256>"}`. `status` accepts that and
  the legacy `{"commit": "8f12c88…"}` and adds `"bridge": {"source": "upstream-git" | "vendored", "tree": … | null,
  "current": true | false}`, where `current` says whether the installed bridge equals the plugin's vendored copy
  (a legacy install counts as the unmodified `8f12c88` tree, recorded as a constant). Everything else in the status
  output and `relay_status.py` is unchanged, so spec-guard's probe is unaffected.
  **Upgrade path, specified here and implemented by the first module that changes the bridge
  (`delivery-state-machine`):** `native_collaboration_runtime.py upgrade --confirm`, run only after the user agrees
  (the collaboration-ops skill asks first). It refuses while any bridge server of this runtime is running; copies
  `runtime/mailbox/` to `$AGENT_RELAY_HOME/backups/<UTC time>/runtime-mailbox/` first; builds the new runtime from
  the verified vendored copy in a stage beside `runtime/`; moves `mailbox/` and `data/` into the stage; renames
  `runtime/` to `runtime.previous-<time>` and the stage to `runtime/`; checks `status` is `ready` and `current`, and
  that the mailbox row counts equal the backup's. Paths stay the same, so host entries need no change. The previous
  directory is kept until the user removes it; on any failure before the swap nothing changes, after it the
  previous directory is renamed back.

## Requirements

1. `plugins/agent-relay/bridge/` holds the vendored files of assumption 2 plus `UPSTREAM.md` and `UPSTREAM.sha256`.
2. New installs carry the D26 manifest; `status` reports `bridge.source`, `tree` and `current` for both kinds
   (tested with a legacy and a vendored fixture).
2b. `install_runtime` no longer runs `git`; it installs from the vendored copy and refuses a copy that does not match
   `UPSTREAM.sha256` (tested: changed, extra and missing file each refused, nothing installed).
3. A unit test checks the vendored tree against `UPSTREAM.sha256`, so an unrecorded edit fails `validate.sh`.
4. D25 (a)–(d) recorded in the todo.
5. The vendored `LICENSE` is upstream's text unchanged; `UPSTREAM.md` names the repository, the commit and the
   change rule; README's licence/credit section points to `plugins/agent-relay/bridge/UPSTREAM.md`. README credit and install text, `collaboration-ops` skill (no `git` needed), interface §13 / brief note updated;
   the interface's `B:path:line` citations now resolve inside the repository.

## Commands

```bash
/bin/bash scripts/validate.sh
AGENT_RELAY_HOME=<tmp> python3 -B plugins/agent-relay/hooks/native_collaboration_runtime.py install
```

## Project structure

New: `plugins/agent-relay/bridge/**`, a test for the vendored tree. Changed: `native_collaboration_runtime.py` and its
tests, `README.md`, `skills/collaboration-ops/SKILL.md`, `docs/collaboration-interface.md`, `tasks/bridge-vendoring/`.

## Testing strategy

- Unit: install from a fixture bridge copy (stubbed `npm`) succeeds; changed / extra / missing file refused with
  nothing written; no `git` call; manifest unchanged; vendored tree matches `UPSTREAM.sha256`.
- Mutation: skipping the hash check lets the tampered-copy test pass → it must fail.
- Live (round 1 owner told first, temporary `AGENT_RELAY_HOME`, no host attach): D25 (b)–(d).

## Boundaries

- Always: keep vendored files byte-identical to upstream in this module; keep the MIT notice.
- Ask first: dropping or adding vendored paths beyond assumption 2; vendoring `node_modules`.
- Never: edit bridge source in this module; touch the real `~/.agent-relay` or host configuration; push without
  approval.

## Success criteria

1. Tests green; tampered copies refused; vendored tree check in `validate.sh`.
2. D25 (a)–(d) pass.
3. Docs updated; no spec-guard change needed.

## Open questions

None.
