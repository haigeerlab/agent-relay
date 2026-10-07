#!/usr/bin/env bash
# Read-only preflight for a real-host acceptance run (docs/acceptance/checklist.md, A1-A4); the work is in preflight.py.
# Prints host versions, where agent-relay is installed on each host and whether each copy is current, Codex
# auto-review, the runtime root, and the exact background Claude launch command for a test identity. Writes nothing.
set -uo pipefail
exec python3 -B "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/preflight.py" "$@"
