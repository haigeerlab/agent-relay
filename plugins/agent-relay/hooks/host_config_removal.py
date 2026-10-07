"""Add and remove host MCP entries that agent-relay installs, and nothing a user changed.

Codex tables are removed only when the file still contains the exact fragment an adapter
would write today, as a complete table; any edited or partial table is left for the user.
Claude servers are added and removed through the Claude CLI, never by editing its state files,
and never after `claude mcp get`: that command health-checks the server, which takes many
seconds for a dead endpoint. `add` and `remove` report an existing or missing name themselves.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


def _codex_table_line(content: str, table_name: str) -> int | None:
    pattern = re.compile(r'^\s*\[mcp_servers\.(?:"' + re.escape(table_name) + '"|'
                         + re.escape(table_name) + r')(?:\.|\])', re.MULTILINE)
    match = pattern.search(content)
    return None if match is None else content.count("\n", 0, match.start()) + 1


_HEADER = re.compile(r'^\s*\[([^\[\]]+)\]\s*(?:#.*)?$')
_KEY = re.compile(r'^\s*("[^"]*"|[A-Za-z0-9_-]+)\s*=\s*(.*?)\s*$')
_APPROVAL = re.compile(r"""^(?:"[^"]*"|'[^']*')\s*(?:#.*)?$""")


def _blocks(content: str) -> list[tuple[int, str | None, list[str]]]:
    """Split TOML text into (first line number, table name or None for the preamble, raw lines with endings)."""
    blocks: list[tuple[int, str | None, list[str]]] = [(1, None, [])]
    for number, line in enumerate(content.splitlines(keepends=True), start=1):
        header = _HEADER.match(line)
        if header:
            blocks.append((number, header.group(1).strip(), [line]))
        else:
            blocks[-1][2].append(line)
    return blocks


def _ours(name: str, table_name: str) -> str | None:
    """The part after the server name ("" for the server table itself) when `name` is one of our tables."""
    for prefix in ("mcp_servers.%s" % table_name, 'mcp_servers."%s"' % table_name):
        if name == prefix:
            return ""
        if name.startswith(prefix + "."):
            return name[len(prefix) + 1:]
    return None


def _pairs(start: int, lines: list[str]) -> list[tuple[int, str, str]]:
    """(line number, key, raw value) of each key line after the header; blank lines and comments skipped."""
    pairs = []
    for offset, line in enumerate(lines[1:], start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _KEY.match(line)
        pairs.append((start + offset, match.group(1).strip('"') if match else stripped.split("=")[0].strip(),
                      match.group(2) if match else "\0"))
    return pairs


def _executable_node(raw: str) -> bool:
    try:
        path = Path(json.loads(raw))
    except (ValueError, TypeError):
        return False
    return path.is_absolute() and path.is_file() and os.access(path, os.X_OK)


def _differences(content: str, fragment: str, table_name: str) -> tuple[list[str], list[tuple[int, str | None, list[str]]]]:
    """Compare our tables with the fragment. Codex's approval subtables (``tools.<name>`` holding only
    ``approval_mode``) are expected; a different ``command`` is accepted when it is an executable node.
    Differences name lines and keys, never values (they may be credentials)."""
    expected = {_ours(name, table_name): {key: value for _, key, value in _pairs(start, lines)}
                for start, name, lines in _blocks(fragment) if name is not None}
    found: list[tuple[int, str | None, list[str]]] = []
    seen: set[str] = set()
    problems: list[str] = []
    for start, name, lines in _blocks(content):
        part = None if name is None else _ours(name, table_name)
        if part is None:
            continue
        found.append((start, name, lines))
        if part in seen:
            problems.append("line %d: duplicate table [%s]" % (start, name))
            continue
        seen.add(part)
        pairs = _pairs(start, lines)
        if part in expected:
            want = expected[part]
            for number, key, value in pairs:
                if key not in want:
                    problems.append("line %d: unexpected key %s" % (number, key))
                elif value != want[key] and not (part == "" and key == "command" and _executable_node(value)):
                    problems.append("line %d: %s differs" % (number, key))
            for key in want:
                if key not in {key for _, key, _ in pairs}:
                    problems.append("line %d: missing %s in [%s]" % (start, key, name))
        elif part.startswith("tools.") and part.count(".") == 1:
            for number, key, value in pairs:
                if key != "approval_mode" or not _APPROVAL.match(value):
                    problems.append("line %d: unexpected key %s in [%s]" % (number, key, name))
        else:
            problems.append("line %d: unexpected table [%s]" % (start, name))
    for part in expected:
        if found and part not in seen:
            problems.append("missing table for %s" % (part or "the server"))
    return problems, found


def remove_codex_table(codex_config: Path, fragment: str, table_name: str) -> str:
    """Return "removed" or "absent"; raise ValueError naming each differing line when the tables are not ours.

    Our tables are the fragment's server and env tables plus any approval subtables Codex wrote for 始终允许
    (round 1 finding 6); they are removed together, wherever they are, and every other byte stays.
    """
    codex_config = Path(codex_config)
    if not codex_config.exists() and not codex_config.is_symlink():
        return "absent"
    metadata = codex_config.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise ValueError("Codex configuration must be an owner-owned regular file, not a symlink")
    content = codex_config.read_text(encoding="utf-8")
    line = _codex_table_line(content, table_name)
    if line is None:
        return "absent"
    problems, ours = _differences(content, fragment, table_name)
    if problems:
        raise ValueError(
            "Codex table [mcp_servers.%s] at line %d differs from what agent-relay installed; remove it manually. "
            "Differences: %s" % (table_name, line, "; ".join(problems)))
    removed = {start for start, _, _ in ours}
    updated = ""
    seam = False
    for start, name, lines in _blocks(content):
        if name is not None and start in removed:
            seam = True
            continue
        text = "".join(lines)
        if seam:
            before, text = updated.rstrip("\n"), text.lstrip("\n")
            updated = before + ("\n\n" if before and text else "\n" if before else "")
            seam = False
        updated += text
    if seam:
        updated = updated.rstrip("\n") + ("\n" if updated.strip() else "")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="config-", suffix=".tmp",
                                     dir=codex_config.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(updated)
    try:
        temporary.chmod(stat.S_IMODE(metadata.st_mode))
        temporary.replace(codex_config)
    finally:
        temporary.unlink(missing_ok=True)
    return "removed"


def add_claude_server(claude_bin: str, arguments: list[str], name: str) -> None:
    """Register a user-scoped server; the Claude CLI itself refuses an existing name."""
    try:
        added = subprocess.run([claude_bin, "mcp", *arguments], check=False,
                               capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("unable to run Claude MCP registration") from error
    if added.returncode == 0:
        return
    output = (added.stdout + added.stderr).strip()
    if "already exists" in output:
        raise ValueError("Claude MCP server %s already exists; refusing to overwrite it" % name)
    raise ValueError("Claude rejected MCP registration for %s: %s"
                     % (name, output.splitlines()[-1] if output else "no output"))


def remove_claude_server(claude_bin: str, name: str) -> str:
    """Return "removed" or "absent" for a user-scoped Claude MCP server."""
    # 不先调用 `claude mcp get`：它会对条目做连接健康检查，失效端点要十几秒，正是需要移除的情形。
    try:
        removed = subprocess.run([claude_bin, "mcp", "remove", "--scope", "user", name],
                                 check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("unable to run Claude MCP removal") from error
    if removed.returncode == 0:
        return "removed"
    if "No MCP server named" in removed.stdout + removed.stderr:
        return "absent"
    raise ValueError("Claude refused to remove the user-scoped MCP server " + name)
