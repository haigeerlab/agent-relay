#!/usr/bin/env bash
# Retire this run's test identities (docs/acceptance/checklist.md, E2).
#
# usage: cleanup.sh <run> [--confirm] [--root <runtime root>]
#
# Lists live identities named ar-acc-<run>-* from the mailbox database (read-only). Only with --confirm does it
# retire them, one exact name at a time through native_collaboration_retire.py; history is kept and no other
# identity is touched. Delegated identities are retired by exact name and listed in the run record.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 -B - "$REPO" "$@" <<'PY'
import argparse
from contextlib import closing
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1])
hooks = repo / "plugins" / "agent-relay" / "hooks"
sys.path.insert(0, str(hooks))
from native_collaboration_runtime import StateHomeError, default_root, open_mailbox_read_only  # noqa: E402

parser = argparse.ArgumentParser(prog="cleanup.sh")
parser.add_argument("run")
parser.add_argument("--confirm", action="store_true")
parser.add_argument("--root", type=Path)
args = parser.parse_args(sys.argv[2:])
try:
    args.root = args.root or default_root()
except StateHomeError as error:
    parser.exit(2, f"{parser.prog}: error: {error}\n")
if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.run):
    parser.error("run id must be lowercase letters, digits and hyphens")
prefix = f"ar-acc-{args.run}-"
database = args.root / "mailbox" / "bridge.sqlite"
try:
    with closing(open_mailbox_read_only(database)) as connection:  # D51's read (acceptance-kit-round2 D57)
        names = [row[0] for row in connection.execute(
            "SELECT name FROM agents WHERE retired_at IS NULL ORDER BY name")
            if row[0].startswith(prefix)]
except sqlite3.Error as exc:
    print(f"cannot read {database}: {exc}")
    sys.exit(2)

print(f"live identities with prefix {prefix}: {len(names)}")
for name in names:
    print(f"  {name}")
if not args.confirm:
    print("preview only; rerun with --confirm to retire them")
    sys.exit(0)
retire = [sys.executable, "-B", str(hooks / "native_collaboration_retire.py")]
failed = 0
for name in names:
    done = subprocess.run(retire + ["--name", name, "--confirm-retire", "--root", str(args.root),
                                    "--note", f"acceptance run {args.run} cleanup"],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True)
    print(f"  {name}: {(done.stdout.strip() or done.stderr.strip())}")
    failed += done.returncode != 0
sys.exit(1 if failed else 0)
PY
