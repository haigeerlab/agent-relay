#!/usr/bin/env python3
"""Tell a caller such as Spec Guard's probe whether the agent-relay mailbox runtime is ready.

Declared as the `status` command in `interface.json` (interface 1.x, decision D4; 1.1 since cleanup-gaps D62, 1.2 since codex-gated-wake D69). Prints one JSON object,
`{"ready": true|false, "setup": "<how to set it up>"}`, from the read-only runtime status; it never creates,
installs, or repairs anything.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_collaboration_runtime import StateHomeError, default_root, status  # noqa: E402

SETUP = ("在 Claude Code 运行 /agent-relay:collaboration，或在 Codex 让 collaboration-ops skill "
         "查看并在你同意后安装运行时")


def main() -> int:
    try:
        result = status(default_root())
    except StateHomeError as error:
        result = {"state": "invalid", "diagnostic": str(error)}
    if result.get("state") == "ready":
        print(json.dumps({"ready": True, "setup": ""}, ensure_ascii=False))
        return 0
    setup = SETUP
    if result.get("state") == "invalid":
        setup = f"运行时无效（{result.get('diagnostic')}）。" + SETUP
    print(json.dumps({"ready": False, "setup": setup}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
