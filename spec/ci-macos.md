# Spec: ci-macos

## Objective

agent-relay has no CI: every check so far ran on the owner's Mac (`scripts/validate.sh` on Python 3.9, 3.10, 3.14 and
the bridge's `npm run check`). Add GitHub Actions on macOS so every pull request and every push to `main` runs the same
validation on the Pythons and Nodes users actually have, and make doctor say which Python and Node it ran with, so a
red run or a user report can be read without guessing. Whether CI becomes a required check on `main` is the user's
decision after it runs green (requested by the user via the round-2 coordinator, 2026-10-08).

Readers: the user; reviewers of every later PR.

## What exists today (measured 2026-10-08)

- No `.github/` directory. `scripts/validate.sh` runs every `hooks/test_*.py` with `python3` from `PATH`, then
  `npm run check` in `plugins/agent-relay/bridge` when its `node_modules` exists (else "skip").
- Bridge `package.json`: `engines.node >=22.5.0`; `npm run check` = typecheck, build, node tests.
- The repository is **public**, so GitHub's standard macOS runners cost no minutes.
- Runner images (`actions/runner-images` README): `macos-15` is arm64 (macOS 15); `macos-26` / `macos-latest` is
  arm64; `macos-14` is deprecated. The `macos-15` arm64 image ships Python 3.14.7, Node 22.23.2 and Xcode Command
  Line Tools, whose `/usr/bin/python3` is Apple's Python 3.9.6, the one on the user's Mac.
- `actions/python-versions` manifest: Python 3.9 has macOS arm64 builds only for 3.9.12 and 3.9.13; 3.14.8 has one.
- Latest releases: `actions/checkout` v7.0.1 (2026-07-20, `3d3c42e5aac5ba805825da76410c181273ba90b1`),
  `actions/setup-python` v7.0.0 (2026-07-20, `5fda3b95a4ea91299a34e894583c3862153e4b97`), `actions/setup-node`
  v7.1.0 (2026-10-08, today) and v7.0.0 (2026-07-14, `820762786026740c76f36085b0efc47a31fe5020`).
- doctor names the node only inside the `probe` check, and only when a runtime is installed; it never names Python.

## Assumptions

1. Runner `macos-15` (pinned, not `-latest`, so the OS does not move under us).
2. Python 3.9 is Apple's `/usr/bin/python3` (3.9.6) from the Command Line Tools on the image, not a `setup-python`
   build: it is the Python macOS users run, and `setup-python` has no current 3.9 arm64 build. The job puts a directory
   with `python3 → /usr/bin/python3` first in `PATH` and fails unless `python3 --version` is 3.9.x.
3. Python 3.14 via `actions/setup-python` (`3.14`); Node 22 and 24 via `actions/setup-node` (`22`, `24`).
4. Actions are pinned by full commit SHA with the version in a comment; `setup-node` uses v7.0.0, not the release from
   today (a release gets a few days before we depend on it).
5. Least privilege: `permissions: contents: read`; `actions/checkout` with `persist-credentials: false`; no secrets,
   no `pull_request_target`.
6. `npm ci` in the bridge needs the network; nothing else does. Each job has a 20-minute timeout; a newer push to the
   same PR cancels the older run.
7. The first CI runs may expose tests that depend on this Mac (paths, installed tools). Fixing those is in scope when
   the fix is test isolation; a product change found that way stops for the user.
8. No version bump: CI and a doctor check are not interface changes (interface stays 1.3).

## Decisions

- **D80 workflow.** `.github/workflows/ci.yml`, on `pull_request` and `push` to `main` (plus `workflow_dispatch`). One
  job matrix on `macos-15`; each job: checkout, Python (assumption 2 or 3), Node, `npm ci` in the bridge, print the
  toolchain via doctor (D81), then `bash scripts/validate.sh`, which must report the bridge check as run, not skipped.
- **D80a matrix.** The full **2 × 2**: Python 3.9 / 3.14 × Node 22 / 24, four jobs in parallel, free on a public
  repo (chosen by the user 2026-10-08 over the two diagonals).
- **D81 doctor names its toolchain.** A new check `toolchain`, always present, never needs a runtime: `ok`
  "python <sys.executable> (<version>); node <path> (<version>, from <source>)" using the same node selection as the
  probe; `warn` when no usable node is found (with the existing install hint). doctor's exit code is unchanged.
- **D82 required check is the user's.** The PR adds no branch protection. After CI is green on the PR, the user decides
  whether to make it required on `main`; the module only documents how (README "Development" note).

## Requirements

1. Python test, red first: doctor reports `toolchain` with `sys.executable`, the Python version and the selected node
   path, version and source; `warn` when node selection fails; present when no runtime is installed.
2. `.github/workflows/ci.yml` per D80/D80a, actions pinned by SHA, read-only permissions; a static test checks the pins
   are 40-hex SHAs, `permissions` is read-only, `persist-credentials: false`, and no `pull_request_target`.
3. The PR's own CI run is green in every matrix job, and each job's log shows the expected Python and Node (from the
   doctor `toolchain` line) and "bridge: npm run check" as ok.
4. README: a short "CI" note (what runs, where) and how the user can make it required. CHANGELOG `[Unreleased]`.
5. Local validation unchanged: `scripts/validate.sh` green on Python 3.9, 3.10, 3.14 here.

## Boundaries

- Always: SHA-pinned actions, read-only token, no secrets.
- Ask first: branch protection or any repository setting; the real `~/.agent-relay`, `~/.claude`, `~/.codex`.
- Never: `pull_request_target`, self-hosted runners, pushing without approval.

## Success criteria

The PR's CI is green in every job with the expected toolchain shown; doctor's `toolchain` check is tested; the user
has what they need to decide about the required check.

## Open questions

None. Accepted by the user on 2026-10-08 (assumptions 1–8, D80–D82, D80a full matrix).
