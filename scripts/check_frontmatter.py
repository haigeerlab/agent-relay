#!/usr/bin/env python3
"""Check the frontmatter of every plugin skill, command and agent file (plugin spec C7).

`claude plugin validate` only warns about a missing description and reads broken YAML without a word, so this
check fails on both. The frontmatter must be a YAML mapping; skills and agents need `name` and `description`;
commands need `description` (a command's name is its file name).

Needs PyYAML. Usage: check_frontmatter.py [plugins-dir]  (default: plugins/ next to this script's parent)
"""
from __future__ import annotations

from pathlib import Path
import sys

import yaml

REQUIRED = {"skill": ("name", "description"), "agent": ("name", "description"), "command": ("description",)}


def files(plugins: Path):
    for plugin in sorted(p for p in plugins.iterdir() if p.is_dir()):
        yield from (("skill", f) for f in sorted(plugin.glob("skills/*/SKILL.md")))
        yield from (("command", f) for f in sorted(plugin.glob("commands/**/*.md")))
        yield from (("agent", f) for f in sorted(plugin.glob("agents/**/*.md")))


def problems(kind: str, path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return ["no frontmatter (the file must start with ---)"]
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return ["frontmatter is not closed with ---"]
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as error:
        return [f"frontmatter is not valid YAML: {' '.join(str(error).split())}"]
    if not isinstance(data, dict):
        return ["frontmatter is not a mapping"]
    return [f"{key} is missing or empty" for key in REQUIRED[kind]
            if not isinstance(data.get(key), str) or not data[key].strip()]


def main() -> int:
    plugins = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "plugins"
    found = failed = 0
    for kind, path in files(plugins):
        found += 1
        for problem in problems(kind, path):
            failed += 1
            print(f"FAIL  {path}: {problem}")
    if found == 0:
        print(f"no skill, command or agent files under {plugins}")
        return 1
    print(f"{found} files checked, {failed} problems")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
