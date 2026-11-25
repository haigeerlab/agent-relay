#!/usr/bin/env python3
"""Select the smallest validate.sh run that covers changed plugin files."""
import argparse
import json
import re
import sys
from pathlib import Path


def decide(paths, hooks_dir):
    """Return (mode, reason, test_files, bridge) for changed repository paths.

    Deleted test files are ignored: they cannot be run, and another mapped path is
    still sufficient to select a quick run. An otherwise empty selection is full.
    """
    paths = list(dict.fromkeys(paths))
    if not paths:
        return "full", "quick fell back: no changed paths", [], False

    hooks = Path(hooks_dir)
    # Cache each source once: closure traversal may inspect it repeatedly.
    sources = {}
    words = {}
    for source in sorted(hooks.glob("*.py")):
        sources[source.stem] = source.read_text(encoding="utf-8")
        # The word set gives the same answer as the word-boundary regex for identifier names, far faster.
        words[source.stem] = set(re.findall(r"[A-Za-z0-9_]+", sources[source.stem]))
    closure = set()
    bridge = False
    unmapped = []
    prefix = "plugins/agent-relay/hooks/"
    for path in paths:
        if path.startswith("plugins/agent-relay/bridge/"):
            bridge = True
            continue
        if not path.startswith(prefix):
            unmapped.append(path)
            continue
        name = path[len(prefix):]
        if "/" in name or not name.endswith(".py"):
            unmapped.append(path)
            continue
        candidate = hooks / name
        if name.startswith("test_"):
            if candidate.is_file():
                closure.add(candidate.stem)
            continue
        closure.add(name[:-3])

    # Hooks and their tests form an import graph. Follow textual references in
    # both directions so changes cover transitive dependents as well.
    def expand(names):
        names = set(names)
        changed = True
        while changed:
            changed = False
            plain = {name for name in names if re.fullmatch(r"[A-Za-z0-9_]+", name)}
            other = names - plain
            for stem, text in sources.items():
                if stem in names:
                    continue
                if not words[stem].isdisjoint(plain) or any(
                        re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", text)
                        for name in other):
                    names.add(stem)
                    changed = True
        return names

    non_test_modules = []
    for path in paths:
        if not path.startswith(prefix):
            continue
        name = path[len(prefix):]
        if "/" not in name and name.endswith(".py") and not name.startswith("test_"):
            non_test_modules.append((path, name[:-3]))
    for path, module in non_test_modules:
        if not any(name.startswith("test_") for name in expand({module})):
            unmapped.append(path)

    if bridge:
        closure.add("native_collaboration_runtime")
    closure = expand(closure)

    selected = sorted(
        stem + ".py" for stem in closure
        if stem.startswith("test_") and stem in sources
    )

    if unmapped:
        # Make a changed validator visible in the common mixed-change fallback.
        path = next((item for item in unmapped if item.startswith("scripts/")), unmapped[0])
        return "full", f"quick fell back: {path} is not mapped", [], False
    if not selected and not bridge:
        return "full", "quick fell back: no runnable selection", [], False
    if bridge and "test_bridge_vendoring" in sources:
        selected = sorted(set(selected) | {"test_bridge_vendoring.py"})
    return "quick", f"from {len(paths)} changed paths", selected, bridge


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hooks-dir", required=True)
    parser.add_argument("--null", action="store_true")
    parser.add_argument("--format", choices=("json", "nul"), default="json")
    args = parser.parse_args()
    separator = "\0" if args.null else "\n"
    paths = [path for path in sys.stdin.read().split(separator) if path]
    decision = decide(paths, args.hooks_dir)
    if args.format == "json":
        print(json.dumps(decision))
    else:
        mode, reason, tests, bridge = decision
        sys.stdout.buffer.write("\0".join([mode, reason, "yes" if bridge else "no", *tests]).encode())
        sys.stdout.buffer.write(b"\0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
