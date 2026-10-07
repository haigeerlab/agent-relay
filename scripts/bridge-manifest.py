#!/usr/bin/env python3
"""Rewrite plugins/agent-relay/bridge/UPSTREAM.sha256 after a deliberate bridge change.

Run it in the same commit that changes the bridge and records the change in UPSTREAM.md
(bridge-vendoring D24). Build outputs and the two provenance files are not listed.
"""
import hashlib
from pathlib import Path
import sys

BRIDGE = Path(__file__).resolve().parent.parent / "plugins" / "agent-relay" / "bridge"
SKIP_DIRS = {"node_modules", "dist", "dist.next", "dist.old"}
SKIP_FILES = {"UPSTREAM.md", "UPSTREAM.sha256"}

lines = []
for path in sorted(BRIDGE.rglob("*")):
    relative = path.relative_to(BRIDGE)
    if relative.parts[0] in SKIP_DIRS or relative.as_posix() in SKIP_FILES or not path.is_file():
        continue
    lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative.as_posix()}")
(BRIDGE / "UPSTREAM.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{len(lines)} files listed", file=sys.stderr)
