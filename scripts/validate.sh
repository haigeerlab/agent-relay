#!/usr/bin/env bash
# Run every agent-relay test file. Tests are found by glob, so a test added by a later module cannot be
# left out; finding none is a failure, not a pass.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--quick" ]; }; then
  echo "usage: bash scripts/validate.sh [--quick]" >&2
  exit 2
fi

# Seal the run (test-isolation D22): every test sees a throwaway home, state root and host config, so
# none can read or write the user's ~/.agent-relay, ~/.claude or ~/.codex. Removed on any exit.
SEAL="$(mktemp -d "${TMPDIR:-/tmp}/ar-validate-XXXXXX")" || exit 1
trap 'rm -rf "$SEAL"' EXIT
mkdir -p "$SEAL/home" "$SEAL/claude" "$SEAL/codex"
export AGENT_RELAY_TEST_SEAL="$SEAL" HOME="$SEAL/home" AGENT_RELAY_HOME="$SEAL/agent-relay" \
  CLAUDE_CONFIG_DIR="$SEAL/claude" CODEX_HOME="$SEAL/codex"

TESTS_GLOB="plugins/agent-relay/hooks/test_*.py"
HOOKS_DIR="plugins/agent-relay/hooks"
QUICK=0
BRIDGE_NEEDED=1
full_fallback() {
  QUICK=0
  BRIDGE_NEEDED=1
  echo "validate: full ($1)"
}
if [ "$#" -eq 1 ]; then
  QUICK=1
  CHANGES="$SEAL/changed-paths"
  : > "$CHANGES"
  if ! git rev-parse --verify --quiet origin/main >/dev/null 2>/dev/null; then
    full_fallback "quick fell back: origin/main is unavailable"
  else
    BASE="$(git merge-base origin/main HEAD 2>/dev/null)" || BASE=""
    if [ -z "$BASE" ]; then
      full_fallback "quick fell back: merge-base is unavailable"
    elif ! {
      git diff --name-only --no-renames -z "$BASE...HEAD" -- >> "$CHANGES" 2>/dev/null &&
        git diff --name-only --no-renames -z --cached -- >> "$CHANGES" 2>/dev/null &&
        git diff --name-only --no-renames -z -- >> "$CHANGES" 2>/dev/null &&
        git ls-files --others --exclude-standard -z >> "$CHANGES" 2>/dev/null
    }; then
      full_fallback "quick fell back: git diff failed"
    fi
  fi
  if [ "$QUICK" -eq 1 ]; then
    SCOPE=()
    while IFS= read -r -d '' scope_item; do
      SCOPE+=("$scope_item")
    done < <(python3 -B scripts/quick_scope.py --hooks-dir "$HOOKS_DIR" --null --format nul < "$CHANGES")
    MODE="${SCOPE[0]:-full}"
    REASON="${SCOPE[1]:-quick fell back: scope selection failed}"
    if [ "$MODE" = "quick" ]; then
      BRIDGE_NEEDED=0
      [ "${SCOPE[2]:-no}" = "yes" ] && BRIDGE_NEEDED=1
      QUICK_TESTS=()
      scope_index=3
      while [ "$scope_index" -lt "${#SCOPE[@]}" ]; do
        QUICK_TESTS+=("${SCOPE[$scope_index]}")
        scope_index=$((scope_index + 1))
      done
      echo "validate: quick (${#QUICK_TESTS[@]} test files, bridge: $([ "$BRIDGE_NEEDED" -eq 1 ] && echo yes || echo no)) $REASON"
    else
      full_fallback "$REASON"
    fi
  fi
fi
F=0
FILES=0
TOTAL=0
SLOWEST="$SEAL/slowest"
: > "$SLOWEST"
if [ "$QUICK" -eq 1 ]; then
  TEST_FILES=("${QUICK_TESTS[@]+"${QUICK_TESTS[@]}"}")
else
  TEST_FILES=()
  for test in $TESTS_GLOB; do
    [ -f "$test" ] && TEST_FILES+=("${test##*/}")
  done
fi
for test_name in "${TEST_FILES[@]+"${TEST_FILES[@]}"}"; do
  test="$HOOKS_DIR/$test_name"
  [ -f "$test" ] || continue
  FILES=$((FILES + 1))
  START="$(python3 -c 'import time; print(time.monotonic())')"
  OUT="$(python3 -B "$test" 2>&1)"
  RC=$?
  END="$(python3 -c 'import time; print(time.monotonic())')"
  printf '%s %s %s\n' "$START" "$END" "$test_name" >> "$SLOWEST"
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
BRIDGE_RAN=0
if [ "$BRIDGE_NEEDED" -eq 1 ] && [ -d "$BRIDGE/node_modules" ]; then
  BRIDGE_RAN=1
  START="$(python3 -c 'import time; print(time.monotonic())')"
  OUT="$(cd "$BRIDGE" && npm run --silent check 2>&1)"
  RC=$?
  END="$(python3 -c 'import time; print(time.monotonic())')"
  printf '%s %s %s\n' "$START" "$END" "bridge: npm run check" >> "$SLOWEST"
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
elif [ "$BRIDGE_NEEDED" -eq 1 ]; then
  printf '  skip  %-52s %s\n' "bridge: npm run check" "(run npm ci in $BRIDGE)"
fi

# Only a full run must find test files; a quick run may select the bridge check alone.
if [ "$QUICK" -eq 1 ] && [ "$FILES" -eq 0 ] && [ "$BRIDGE_RAN" -eq 0 ]; then
  echo "validate: quick mode ran nothing"
  echo "validate: FAIL"
  exit 1
fi
if [ "$QUICK" -eq 0 ] && [ "$FILES" -eq 0 ]; then
  echo "no test files matched ${TESTS_GLOB}"
  exit 1
fi
echo "${FILES} files, ${TOTAL} tests"
echo "slowest:"
python3 - "$SLOWEST" <<'PY'
import sys

records = []
with open(sys.argv[1], encoding="utf-8") as timings:
    for line in timings:
        start, end, name = line.rstrip("\n").split(" ", 2)
        records.append((float(end) - float(start), name))
for elapsed, name in sorted(records, reverse=True)[:5]:
    print(f"  {elapsed:.1f}s  {name}")
PY
if [ "$F" -eq 0 ]; then echo "validate: pass"; else echo "validate: FAIL"; fi
exit "$F"
