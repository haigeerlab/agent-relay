#!/usr/bin/env python3
"""Keep a scoped Claude Code review inside its scope (delegation-hygiene D167).

A PreToolUse hook the delegation controller passes to a scoped review with `--settings`. It denies Read, Grep and Glob
on any target outside the scope, comparing real paths (symlinks resolved), and denies malformed input. In `dontAsk`
mode reading inside the project needs no allow, so an allow list cannot narrow it; this hook can (measured
2026-10-09). Other tools are left to the session's own permissions. Prints a deny decision, or nothing to allow.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

FILE_TOOLS = ("Read", "Grep", "Glob")
GLOB_CHARACTERS = "*?[{"


def _deny() -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "outside the review scope",
    }}))
    return 0


def _glob_base(pattern: str) -> str:
    """The directory part of a glob pattern before its first wildcard."""
    cut = min((pattern.index(c) for c in GLOB_CHARACTERS if c in pattern), default=len(pattern))
    return os.path.dirname(pattern[:cut]) if cut < len(pattern) else pattern


def _target(tool: str, tool_input: dict, root: Path) -> Path | None:
    if tool == "Read":
        raw = tool_input.get("file_path")
    else:
        raw = tool_input.get("path")
        if tool == "Glob" and not raw:
            pattern = tool_input.get("pattern")
            if not isinstance(pattern, str):
                return None
            # An absolute (or ~) pattern searches where it says, whatever the working directory.
            raw = _glob_base(pattern) if pattern.startswith(("/", "~")) else None
        if raw is None:
            return root
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(os.path.expanduser(raw))
    return (path if path.is_absolute() else root / path).resolve()


def _inside(target: Path, scope: list[Path]) -> bool:
    return any(target == allowed or allowed in target.parents for allowed in scope)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--scope", action="append", default=[])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    scope = [(root / item).resolve() for item in args.scope]
    try:
        event = json.loads(sys.stdin.read())
        tool = event["tool_name"]
        tool_input = event["tool_input"]
        if not isinstance(tool, str) or not isinstance(tool_input, dict):
            return _deny()
    except (ValueError, KeyError, TypeError):
        return _deny()
    if tool not in FILE_TOOLS:
        return 0
    target = _target(tool, tool_input, root)
    if target is None or not scope or not _inside(target, scope):
        return _deny()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
