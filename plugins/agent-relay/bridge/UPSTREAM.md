# Vendored bridge: provenance

This directory is a copy of the MIT-licensed
[claude-codex-mcp-bridge](https://github.com/WebisityStudio/claude-codex-mcp-bridge) by Tesla Major
(see [LICENSE](LICENSE)), kept inside agent-relay so that agent-relay maintains it (module `bridge-vendoring`).

| Field | Value |
|---|---|
| Upstream repository | https://github.com/WebisityStudio/claude-codex-mcp-bridge |
| Upstream commit | `8f12c880cfdba73812b6ab7bc0f373fc467e0343` |
| Vendored on | 2026-10-07, from the commit's git blobs (every file's blob hash checked equal) |
| Licence | MIT, notice kept unchanged in `LICENSE` |
| File hashes | `UPSTREAM.sha256` (SHA-256 of every vendored file; the installer refuses a copy that differs) |

Left out on purpose (not read by the build or the runtime): `skills/` and `agents/` (worker features that
agent-relay denies), `assets/` and `scripts/generate-demo-gif.py` (demo media), `.github/` (upstream CI). The
README's logo link therefore points at a file that is not here.

## agent-relay changes

A module that changes the bridge records the change here and rewrites `UPSTREAM.sha256` in the same commit
(`python3 -B scripts/bridge-manifest.py`). Files not listed below are byte-identical to the upstream commit.

| Module | Files | Change |
|---|---|---|
| `delivery-state-machine` | `src/schema.ts`, `test/schema.test.ts` | Schema v3: nullable `messages.delivery_state`, `delivery_changed_at`, `read_at`, `expires_at` and an index; tests for the v2 → v3 migration and older-process inserts |
| `delivery-state-machine` | `src/delivery.ts` (new), `src/bridge-store.ts`, `src/server.ts`, `test/delivery-state.test.ts` (new) | Delivery state and its one transition table (D28); a direct send starts `queued` with `expires_at` (24 h default, `BRIDGE_QUEUE_TIMEOUT_MS`, per-send `expiresInSeconds`); messages carry `deliveryState` and `expiresAt` |
| `delivery-state-machine` | `src/wake-queue.ts`, `test/delivery-wake.test.ts` (new) | Wake outcomes and recipient fetches move the message state (claim → `sending`; pending/held → `queued`; accepted/read → `accepted`; refused → `failed`; lapsed lease or no receipt → `unknown`, never re-claimed); evidence resolves `unknown` → `accepted`; fetch records `read_at` |
