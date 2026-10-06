#!/usr/bin/env bash
# Collaboration test files, run as one suite. Collaboration-owned: moves to agent-relay with the code
# (collaboration-extraction), and scripts/validate.sh calls this file instead of naming the tests itself,
# so no Spec Guard runner refers to collaboration internals (collaboration-boundary).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.." || exit 1
F=0
python3 -B plugins/spec-guard/hooks/test_collab_entry.py || F=1
python3 -B plugins/spec-guard/hooks/test_native_collab_entry.py || F=1
python3 -B plugins/spec-guard/hooks/test_skill_entrypoints.py || F=1
python3 -B plugins/spec-guard/hooks/test_session_routing.py || F=1
python3 -B plugins/spec-guard/hooks/test_session_routing_entry.py || F=1
python3 -B plugins/spec-guard/hooks/test_session_delegation.py || F=1
python3 -B plugins/spec-guard/hooks/test_session_delegation_codex.py || F=1
python3 -B plugins/spec-guard/hooks/test_session_delegation_claude.py || F=1
python3 -B plugins/spec-guard/hooks/test_session_delegation_backend.py || F=1
python3 -B plugins/spec-guard/hooks/test_session_delegation_recovery.py || F=1
python3 -B plugins/spec-guard/hooks/test_native_collaboration_runtime.py || F=1
python3 -B plugins/spec-guard/hooks/test_native_collaboration_adapters.py || F=1
python3 -B plugins/spec-guard/hooks/test_native_collaboration_retire.py || F=1
python3 -B plugins/spec-guard/hooks/test_native_only_collaboration.py || F=1
python3 -B plugins/spec-guard/hooks/test_native_collaboration_host_config.py || F=1
exit "$F"
