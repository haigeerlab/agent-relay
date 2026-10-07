"""Read-only preflight for a real-host acceptance run (docs/acceptance/checklist.md, A1-A4).

Prints host versions, where agent-relay is installed on each host and whether each copy a host runs matches this
checkout, Codex auto-review, the runtime root, and the exact background Claude launch command for a test identity.
Writes nothing.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "plugins" / "agent-relay"
sys.path.insert(0, str(SOURCE / "hooks"))
from native_collaboration_adapters import CLAUDE_SERVER_NAME  # noqa: E402
from native_collaboration_runtime import MAILBOX_TOOLS, StateHomeError, default_root  # noqa: E402

# Build output and what hosts add to their own copies (Codex writes migrated-command-skills/), never compared.
IGNORED = frozenset(("node_modules", ".git", "__pycache__", ".DS_Store", "migrated-command-skills"))


def tree_hash(root):
    """sha256 over every file's relative path and bytes, ignoring IGNORED names; None when root is not a directory."""
    root = Path(root)
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED for part in relative.parts) or not path.is_file():
            continue
        digest.update(str(relative).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


SOURCE_HASH = tree_hash(SOURCE)


def compared(path, refresh):
    found = tree_hash(path)
    if found is None:
        return f"{path}  missing"
    if found == SOURCE_HASH:
        return f"{path}  current"
    return f"{path}  STALE (differs from this checkout; refresh: {refresh})"


def run(*command):
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"unavailable ({exc.__class__.__name__})"
    return done, (done.stdout.strip() or done.stderr.strip()).splitlines()[0] if (done.stdout or done.stderr) else ""


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _directory_plugin(marketplace):
    """The agent-relay directory inside a `directory` marketplace: what Claude sessions load (Task 1 probe)."""
    source = (marketplace or {}).get("source") or {}
    if source.get("source") != "directory" or not source.get("path"):
        return None
    root = Path(source["path"])
    try:
        catalog = _json(root / ".claude-plugin" / "marketplace.json") or {}
    except (OSError, ValueError):
        return None
    for plugin in catalog.get("plugins", []):
        if isinstance(plugin, dict) and plugin.get("name") == "agent-relay" and isinstance(plugin.get("source"), str):
            return (root / plugin["source"]).resolve()
    return None


def claude_install():
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        record = _json(home / "plugins" / "installed_plugins.json")
        marketplaces = _json(home / "plugins" / "known_marketplaces.json") or {}
    except (OSError, ValueError) as exc:
        return [f"unknown ({exc.__class__.__name__})"]
    if record is None:
        return ["not installed"]
    lines, loaded = [], []
    for key, items in record.get("plugins", {}).items():
        name, _, market = key.partition("@")
        if name != "agent-relay":
            continue
        plugin_dir = _directory_plugin(marketplaces.get(market))
        if plugin_dir is not None and plugin_dir not in loaded:
            loaded.append(plugin_dir)
            lines.append("loaded   " + compared(plugin_dir, "update that checkout to this commit"))
        for item in (items if isinstance(items, list) else []):
            install = item.get("installPath")
            head = " ".join(str(part) for part in (key, item.get("scope"), item.get("version"),
                                                     item.get("gitCommitSha")) if part)
            if plugin_dir is not None:
                lines.append(f"record   {head} {install}  (not loaded: a directory marketplace is read from its source)")
            else:
                lines.append(f"record   {head} " + compared(install, f"claude plugin install {key}"))
    return lines or ["not installed"]


def codex_install():
    done, first = run("codex", "plugin", "list", "--json")
    if done is None or done.returncode != 0:
        return [f"unknown ({first})"]
    try:
        plugins = json.loads(done.stdout).get("installed", [])
    except (ValueError, AttributeError):
        return ["unknown (no JSON)"]
    lines = []
    for plugin in plugins:
        if not isinstance(plugin, dict) or plugin.get("name") != "agent-relay":
            continue
        plugin_id = plugin.get("pluginId") or "agent-relay"
        source = (plugin.get("source") or {}).get("path")
        lines.append(f"{plugin_id} {plugin.get('version')} enabled={plugin.get('enabled')} {source}")
        market = plugin_id.partition("@")[2]
        cache = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "plugins" / "cache" / market / "agent-relay"
        for copy in sorted(cache.glob("*")) if market and cache.is_dir() else []:
            lines.append("loaded   " + compared(copy, f"codex plugin add {plugin_id}"))
    return lines or ["not installed"]


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


def block(label, lines):
    pad = " " * 22
    return "\n".join((f"{label:<22}" if index == 0 else pad) + line for index, line in enumerate(lines))


def main():
    tools = ",".join(["ListAgents", "SendMessage"] + [f"mcp__{CLAUDE_SERVER_NAME}__{t}" for t in MAILBOX_TOOLS])
    try:
        root = default_root()
        root_line = f"{root} ({'present' if root.exists() else 'absent'})"
    except StateHomeError as error:
        root_line = f"error: {error}"
    print(f"claude version        {run('claude', '--version')[1]}")
    print(f"codex version         {run('codex', '--version')[1]}")
    print(f"this checkout         {SOURCE} (tree {SOURCE_HASH[:12]})")
    print(block("agent-relay (Claude)", claude_install()))
    print(block("agent-relay (Codex)", codex_install()))
    print(f"codex approvals       {codex_reviewer()}")
    print(f"runtime root          {root_line}")
    print("claude test session   claude --bg --permission-mode dontAsk "
          f"--allowedTools \"{tools}\"")
    print("                      (never pass --tools \"\": it removes ListAgents and SendMessage)")


if __name__ == "__main__":
    main()
