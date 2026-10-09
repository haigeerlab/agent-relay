"""Decide whether a CI run tests or skips (ci-on-demand D135, D136).

A run skips only when it is a pull request or a push to main and every changed path is exempt: process and record
files that nothing `scripts/validate.sh` runs reads. Anything else, including any doubt about the change list, runs
the full matrix.

Reads CI_EVENT, CI_BASE and CI_HEAD from the environment (never from the command line, so event data is not
interpolated into shell), prints `scope=full|skip` and the reason, and appends `scope=...` to $GITHUB_OUTPUT when set.
Always exits 0 unless it cannot write that output.
"""
import os
import subprocess
import sys

# The exempt paths (assumption 3), guarded by hooks/test_ci_exempt_guard.py (D137). Adding one is the user's call.
EXEMPT_FILES = ("CLAUDE.md", "AGENTS.md")
EXEMPT_DIRS = ("spec/", "tasks/", ".agent/")

SKIPPABLE_EVENTS = ("pull_request", "push")


def is_exempt(path):
    return path in EXEMPT_FILES or path.startswith(EXEMPT_DIRS)


def decide(event, paths):
    """Return (scope, reason) for a GitHub event name and its changed paths (None when they could not be read)."""
    if event not in SKIPPABLE_EVENTS:
        return "full", f"event {event or '(none)'} always runs the full matrix"
    if paths is None:
        return "full", "the change list could not be read"
    if not paths:
        return "full", "the change list is empty"
    for path in paths:
        if not is_exempt(path):
            return "full", f"{path} is not exempt"
    return "skip", f"all {len(paths)} changed paths are exempt"


def changed_paths(event, base, head):
    """Paths changed by a pull request (since the merge base) or a push (since `before`); None if unknown."""
    if not base or not head or set(base) == {"0"}:
        return None
    revisions = f"{base}...{head}" if event == "pull_request" else f"{base}..{head}"
    # --no-renames: a move out of a checked directory must show its old path too.
    result = subprocess.run(["git", "diff", "--name-only", "--no-renames", revisions, "--"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


def main():
    event = os.environ.get("CI_EVENT", "")
    paths = changed_paths(event, os.environ.get("CI_BASE", ""), os.environ.get("CI_HEAD", "")) \
        if event in SKIPPABLE_EVENTS else None
    scope, reason = decide(event, paths)
    print(f"scope={scope}: {reason}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"scope={scope}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
