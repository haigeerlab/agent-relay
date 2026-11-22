#!/usr/bin/env python3
"""Fail when a tracked file names a local macOS home directory (S107 path privacy).

The repository is public, so `/Users/<name>/...` and its encoded form `-Users-<name>-...` (Claude's project
directory names) must not carry a real account name. Write a placeholder instead: `~/...`, `$HOME/...`,
`<repo>/...` or `/Users/<user>/...` (angle brackets never match). The names in ALLOWED are the made-up ones the
tests use. No real account name belongs in this file or its test: the patterns are generic.

Prints `path:line: kind` for each hit, never the line itself (CI logs are public too), and exits 1 on any hit.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

ALLOWED = frozenset({"example", "someone", "private", "x"})

PATTERNS = (
    ("path", re.compile(r"/Users/([A-Za-z0-9._-]+)")),
    ("encoded", re.compile(r"-Users-([A-Za-z0-9_]+)-")),
)


def hits_in_text(text):
    """(line number, kind) of every local home path in text whose name is not allowed."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in PATTERNS:
            if any(match.group(1) not in ALLOWED for match in pattern.finditer(line)):
                found.append((number, kind))
    return found


def tracked_files(repo=REPO):
    result = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, check=True)
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def scan(repo=REPO, names=None):
    """`path:line: kind` for every hit in the given (default: all tracked) files; binary files are skipped."""
    out = []
    for name in tracked_files(repo) if names is None else names:
        path = Path(repo) / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        for number, kind in hits_in_text(data.decode("utf-8", errors="replace")):
            out.append(f"{name}:{number}: {kind}")
    return out


def main():
    hits = scan()
    for hit in hits:
        print(hit)
    if hits:
        print(f"{len(hits)} local home path(s) found; replace the account name with a placeholder such as "
              "~/..., $HOME/... or /Users/<user>/...", file=sys.stderr)
        return 1
    print("local paths: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
