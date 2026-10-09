#!/usr/bin/env python3
"""Tell a caller such as Spec Guard's probe whether the agent-relay mailbox runtime is ready.

Declared as the `status` command in `interface.json` (interface 1.x, decision D4; 1.1 since cleanup-gaps D62, 1.2 since codex-gated-wake D69, 1.3 since acceptance-030-gaps D75/D77, 1.4 since inbox-read-receipt D101 and
upgrade-recovery; 2.0 since delegation-hygiene D170, with this command and its output unchanged). Prints one JSON object,
`{"ready": true|false, "setup": "<how to set it up>"}`, from the read-only runtime status; it never creates,
installs, or repairs anything.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_collaboration_runtime import NativeRuntimeError, StateHomeError, default_root, status  # noqa: E402

SETUP = ("在 Claude Code 运行 /agent-relay:collaboration，或在 Codex 让 collaboration-ops skill "
         "查看并在你同意后安装运行时")
# upgrade-recovery: an interrupted swap refuses install; only recover gets the runtime back.
RECOVER = ("上次升级／重装／回滚中途停止：先关闭所有使用信箱的会话，再运行 "
           "native_collaboration_runtime.py recover --confirm 恢复到之前的运行时")


def main() -> int:
    try:
        result = status(default_root())
    except StateHomeError as error:
        result = {"state": "invalid", "diagnostic": str(error)}
    except NativeRuntimeError as error:  # an unreadable runtime-swap.json: neither install nor recover can act on it
        print(json.dumps({"ready": False, "setup": f"运行时切换记录无法读取（{error}）。请把 runtime-swap.json 交给"
                          "维护者检查，不要移动运行时目录"}, ensure_ascii=False))
        return 0
    if result.get("state") == "ready":
        print(json.dumps({"ready": True, "setup": ""}, ensure_ascii=False))
        return 0
    setup = SETUP
    if result.get("state") == "interrupted":
        setup = RECOVER
    elif result.get("state") == "invalid":
        setup = f"运行时无效（{result.get('diagnostic')}）。" + SETUP
    print(json.dumps({"ready": False, "setup": setup}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
