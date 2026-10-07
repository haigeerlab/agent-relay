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

None: every vendored file is byte-identical to the upstream commit. A module that changes the bridge records the
change here and updates `UPSTREAM.sha256` in the same commit.
