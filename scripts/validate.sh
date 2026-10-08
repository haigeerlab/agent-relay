#!/usr/bin/env bash
# Run every agent-relay test file. Tests are found by glob, so a test added by a later module cannot be
# left out; finding none is a failure, not a pass.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

# Seal the run (test-isolation D22): every test sees a throwaway home, state root and host config, so
# none can read or write the user's ~/.agent-relay, ~/.claude or ~/.codex. Removed on any exit.
SEAL="$(mktemp -d "${TMPDIR:-/tmp}/ar-validate-XXXXXX")" || exit 1
trap 'rm -rf "$SEAL"' EXIT
mkdir -p "$SEAL/home" "$SEAL/claude" "$SEAL/codex"
export AGENT_RELAY_TEST_SEAL="$SEAL" HOME="$SEAL/home" AGENT_RELAY_HOME="$SEAL/agent-relay" \
  CLAUDE_CONFIG_DIR="$SEAL/claude" CODEX_HOME="$SEAL/codex"

TESTS_GLOB="plugins/agent-relay/hooks/test_*.py"
F=0
FILES=0
TOTAL=0
for test in $TESTS_GLOB; do
  [ -f "$test" ] || continue
  FILES=$((FILES + 1))
  OUT="$(python3 -B "$test" 2>&1)"
  RC=$?
  RAN="$(printf '%s\n' "$OUT" | sed -n 's/^Ran \([0-9][0-9]*\) tests\{0,1\}.*/\1/p' | tail -1)"
  TOTAL=$((TOTAL + ${RAN:-0}))
  if [ "$RC" -eq 0 ]; then
    printf '  ok    %-52s %s\n' "${test##*/}" "${RAN:-?}"
  else
    printf '  FAIL  %-52s %s\n' "${test##*/}" "${RAN:-?}"
    printf '%s\n' "$OUT" | sed 's/^/        /'
    F=1
  fi
done

# The vendored bridge's TypeScript suite (typecheck, build, node tests), inside the same seal. It needs the
# bridge's dev dependencies: `npm ci` in plugins/agent-relay/bridge; without them it is reported as skipped.
BRIDGE="plugins/agent-relay/bridge"
if [ -d "$BRIDGE/node_modules" ]; then
  OUT="$(cd "$BRIDGE" && npm run --silent check 2>&1)"
  RC=$?
  # Node 24 prints "ℹ tests N"; Node 22 prints TAP ("# tests N") when its output is not a terminal (found on CI).
  RAN="$(printf '%s\n' "$OUT" | sed -nE 's/^(ℹ|#) tests ([0-9]+)$/\2/p' | tail -1)"
  TOTAL=$((TOTAL + ${RAN:-0}))
  if [ "$RC" -eq 0 ]; then
    printf '  ok    %-52s %s\n' "bridge: npm run check" "${RAN:-?}"
  else
    printf '  FAIL  %-52s %s\n' "bridge: npm run check" "${RAN:-?}"
    printf '%s\n' "$OUT" | tail -40 | sed 's/^/        /'
    F=1
  fi
else
  printf '  skip  %-52s %s\n' "bridge: npm run check" "(run npm ci in $BRIDGE)"
fi

if [ "$FILES" -eq 0 ]; then
  echo "no test files matched ${TESTS_GLOB}"
  exit 1
fi
echo "${FILES} files, ${TOTAL} tests"
if [ "$F" -eq 0 ]; then echo "validate: pass"; else echo "validate: FAIL"; fi
exit "$F"
