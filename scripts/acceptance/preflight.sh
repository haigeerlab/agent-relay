#!/usr/bin/env bash
# Read-only preflight for a real-host acceptance run (docs/acceptance/checklist.md, A1-A4).
# Prints host versions, where agent-relay is installed on each host, Codex auto-review, the runtime root,
# and the exact background Claude launch command for a test identity. Writes nothing.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 -B - "$REPO" <<'PY'
import json
import os
import re
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "plugins" / "agent-relay" / "hooks"))
from native_collaboration_adapters import CLAUDE_SERVER_NAME  # noqa: E402
from native_collaboration_runtime import MAILBOX_TOOLS, default_root  # noqa: E402


def run(*command):
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"unavailable ({exc.__class__.__name__})"
    return done, (done.stdout.strip() or done.stderr.strip()).splitlines()[0] if (done.stdout or done.stderr) else ""


def claude_install():
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        record = json.loads((home / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "not installed"
    except (OSError, ValueError) as exc:
        return f"unknown ({exc.__class__.__name__})"
    found = [f"{key} {item.get('version')} {item.get('gitCommitSha') or ''} {item.get('installPath')}".strip()
             for key, items in record.get("plugins", {}).items() if key.split("@", 1)[0] == "agent-relay"
             for item in (items if isinstance(items, list) else [])]
    return "; ".join(found) or "not installed"


def codex_install():
    done, first = run("codex", "plugin", "list", "--json")
    if done is None or done.returncode != 0:
        return f"unknown ({first})"
    try:
        plugins = json.loads(done.stdout).get("installed", [])
    except (ValueError, AttributeError):
        return "unknown (no JSON)"
    found = [f"{p.get('pluginId')} {p.get('version')} enabled={p.get('enabled')} {(p.get('source') or {}).get('path')}"
             for p in plugins if isinstance(p, dict) and p.get("name") == "agent-relay"]
    return "; ".join(found) or "not installed"


def codex_reviewer():
    config = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    try:
        text = config.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "no config.toml"
    except OSError as exc:
        return f"unknown ({exc.__class__.__name__})"
    match = re.search(r'^\s*approvals_reviewer\s*=\s*"([^"]*)"', text, re.M)
    value = match.group(1) if match else "unset"
    note = "  <- counts as auto-approval (finding 1): set the App selector to 请求批准 for the run" \
        if value == "guardian_subagent" else ""
    return value + note


tools = ",".join(["ListAgents", "SendMessage"] + [f"mcp__{CLAUDE_SERVER_NAME}__{t}" for t in MAILBOX_TOOLS])
root = default_root()
print(f"claude version        {run('claude', '--version')[1]}")
print(f"codex version         {run('codex', '--version')[1]}")
print(f"agent-relay (Claude)  {claude_install()}")
print(f"agent-relay (Codex)   {codex_install()}")
print(f"codex approvals       {codex_reviewer()}")
print(f"runtime root          {root} ({'present' if root.exists() else 'absent'})")
print("claude test session   claude --bg --permission-mode dontAsk "
      f"--allowedTools \"{tools}\"")
print("                      (never pass --tools \"\": it removes ListAgents and SendMessage)")
PY
