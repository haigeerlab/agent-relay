"""Remove host MCP entries that Spec Guard installed, and nothing a user changed.

Codex tables are removed only when the file still contains the exact fragment an adapter
would write today, as a complete table; any edited or partial table is left for the user.
Claude servers are removed through the Claude CLI, never by editing its state files.
"""
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


def remove_codex_table(codex_config: Path, fragment: str, table_name: str) -> str:
    """Return "removed" or "absent"; raise ValueError when the table is not exactly ours."""
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
    start = content.find(fragment)
    end = start + len(fragment)
    remainder = content[end:].lstrip("\n")
    # 删除后若仍有同名表（重复片段、带引号的子表或被扩展的表），都交给用户手动处理。
    if (start < 0 or (start > 0 and content[start - 1] != "\n") or
            (remainder and not remainder.startswith("[")) or
            _codex_table_line(content[:start] + content[end:], table_name) is not None):
        raise ValueError(
            "Codex table [mcp_servers.%s] at line %d differs from what Spec Guard installed; "
            "remove it manually" % (table_name, line))
    before = content[:start].rstrip("\n")
    updated = before + ("\n\n" if before and remainder else "\n" if before else "") + remainder
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
