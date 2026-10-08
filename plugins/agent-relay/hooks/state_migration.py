#!/usr/bin/env python3
"""Move Spec Guard-era collaboration data into agent-relay: detect, back up, copy, verify, report.

`detect` is read-only. `migrate --confirm` re-runs every check and writes only when there is no blocker. The old
directories under ~/.spec-guard are never modified or deleted; host entries and permission rules are reported,
not changed (spec/state-migration.md, decisions D12-D14).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_collaboration_runtime as _runtime  # noqa: E402
from native_collaboration_runtime import (  # noqa: E402
    StateHomeError, open_mailbox_read_only, state_home, status as runtime_status)
from session_delegation import DATABASE_FILENAME, DelegationError, DelegationStore  # noqa: E402

# Migration source: the names Spec Guard used before the split (D1).
OLD_RUNTIME = Path(".spec-guard") / "native-collaboration"
OLD_DELEGATION = Path(".spec-guard") / "session-delegation" / DATABASE_FILENAME
OLD_CLAUDE_SERVER = "spec-guard-native-collaboration"
OLD_CODEX_TABLE = "spec_guard_native_collaboration"
NEW_CLAUDE_SERVER = "agent-relay"
NEW_CODEX_TABLE = "agent_relay"
NEW_PARENT = Path(".agent-relay")

TERMINAL_DELEGATION_STATES = frozenset(("completed", "cancelled"))
NON_FINAL_WAKE_STATES = ("pending", "sending", "accepted", "unknown")
# state-migration-safety D118: the swap journal and the stage beside the target.
JOURNAL_NAME = "state-migration.json"
STAGE_PREFIX = ".state-migration-"
FAILED_PREFIX = ".state-migration-failed-"


@dataclass
class Report:
    home: Path
    target_root: Path | None = None
    old_mailbox: dict[str, int] | None = None
    old_delegation: dict[str, int] | None = None
    wake_jobs: dict[str, int] = field(default_factory=dict)
    open_delegations: list[dict] = field(default_factory=list)
    running_servers: int = 0
    target_servers: int = 0
    target_runtime: str = "absent"
    target_mailbox: dict[str, int] | None = None
    target_delegation_present: bool = False
    hosts: dict[str, bool] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        data = {key: value for key, value in self.__dict__.items()
                if key not in ("home", "target_root")}
        data["verdict"] = "ready" if not self.blockers else "blocked"
        return data


def default_target() -> Path:
    """The migration target when the CLI is not given a home: the state root (D21)."""
    return state_home()


def _paths(home: Path, target: Path | None = None) -> dict[str, Path]:
    parent = home / NEW_PARENT if target is None else target
    return {"old_runtime": home / OLD_RUNTIME, "old_delegation": home / OLD_DELEGATION,
            "parent": parent, "runtime": parent / "runtime", "delegation": parent / "delegation",
            "backups": parent / "backups"}


def _read_only(path: Path) -> sqlite3.Connection:
    return open_mailbox_read_only(path)


def _snapshot(database: Path, workdir: Path) -> Path:
    """Copy a SQLite file with its WAL and SHM by plain reads, so the source directory is never touched.

    Opening a WAL database, even read-only, can create or update its -wal/-shm files next to it; the old
    Spec Guard directories must stay byte-identical, so every read goes through this copy.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    copy = workdir / database.name
    for suffix in ("", "-wal", "-shm"):
        source = Path(str(database) + suffix)
        if source.is_file():
            shutil.copyfile(source, Path(str(copy) + suffix))
    return copy


def table_counts(path: Path) -> dict[str, int]:
    with _read_only(path) as connection:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}


def _running_servers(old_runtime: Path) -> int:
    done = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True, check=False)
    marker = str(old_runtime / "dist" / "server.js")
    return sum(marker in line for line in done.stdout.splitlines())


def _host_entries(home: Path) -> dict[str, bool]:
    entries = {}
    try:
        servers = json.loads((home / ".claude.json").read_text(encoding="utf-8")).get("mcpServers", {})
    except (OSError, ValueError):
        servers = {}
    entries["claude_old"] = OLD_CLAUDE_SERVER in servers
    entries["claude_new"] = NEW_CLAUDE_SERVER in servers
    try:
        config = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    except OSError:
        config = ""
    for key, table in (("codex_old", OLD_CODEX_TABLE), ("codex_new", NEW_CODEX_TABLE)):
        entries[key] = re.search(r'^\s*\[mcp_servers\.(?:"' + table + '"|' + table + r')\]', config, re.M) is not None
    return entries


def inspect(home: Path, acknowledged: tuple[str, ...] = (),
            process_count: Callable[[Path], int] = _running_servers, *,
            target: Path | None = None, target_count: Callable[[Path], int] | None = None) -> Report:
    paths = _paths(home, target)
    report = Report(home, paths["parent"])
    with tempfile.TemporaryDirectory(prefix="agent-relay-detect-") as scratch:
        _inspect_old(paths, report, acknowledged, Path(scratch))
    if report.old_mailbox is None and report.old_delegation is None:
        report.blockers.append("no Spec Guard collaboration state found; nothing to migrate")
    report.running_servers = process_count(paths["old_runtime"])
    if report.running_servers:
        report.blockers.append(f"{report.running_servers} old bridge server process(es) are running; close or restart "
                               "the sessions that use the old mailbox first (D13)")
    # state-migration-safety D117: the target mailbox is swapped, so agent-relay's own bridges must be closed too.
    report.target_servers = (target_count or _runtime._servers_running)(paths["runtime"])
    if report.target_servers:
        report.blockers.append(f"{report.target_servers} agent-relay bridge server process(es) are running; close "
                               "every session using the mailbox first")
    target = runtime_status(paths["runtime"])
    report.target_runtime = target.get("state", "unknown")
    if report.target_runtime != "ready":
        report.blockers.append("agent-relay runtime is not ready; install it with collaboration-ops first (D14)")
    target_mailbox = paths["runtime"] / "mailbox" / "bridge.sqlite"
    if target_mailbox.is_file():
        report.target_mailbox = table_counts(target_mailbox)
        if report.target_mailbox.get("messages", 0) or report.target_mailbox.get("agents", 0):
            report.blockers.append("agent-relay mailbox already has messages or agents; it is never merged (D14)")
    report.target_delegation_present = (paths["delegation"] / DATABASE_FILENAME).exists()
    if report.target_delegation_present:
        report.blockers.append("agent-relay delegation database already exists; it is never merged (D14)")
    report.hosts = _host_entries(home)
    return report


def _inspect_old(paths: dict[str, Path], report: Report, acknowledged: tuple[str, ...], scratch: Path) -> None:
    source = paths["old_runtime"] / "mailbox" / "bridge.sqlite"
    if source.is_file():
        mailbox = _snapshot(source, scratch / "mailbox")
        report.old_mailbox = table_counts(mailbox)
        with _read_only(mailbox) as connection:
            report.wake_jobs = dict(connection.execute(
                "SELECT state, COUNT(*) FROM wake_jobs WHERE state IN (%s) GROUP BY state"
                % ",".join("?" * len(NON_FINAL_WAKE_STATES)), NON_FINAL_WAKE_STATES).fetchall())
    if paths["old_delegation"].is_file():
        delegation = _snapshot(paths["old_delegation"], scratch / "delegation")
        report.old_delegation = table_counts(delegation)
        with _read_only(delegation) as connection:
            rows = connection.execute(
                "SELECT delegation_id, state, host_ref IS NOT NULL OR host_session_ref IS NOT NULL FROM delegations"
            ).fetchall()
        for delegation_id, state, launched in rows:
            if state in TERMINAL_DELEGATION_STATES:
                continue
            item = {"id": delegation_id[:6], "state": state, "launched": bool(launched),
                    "acknowledged": any(delegation_id.startswith(prefix) for prefix in acknowledged)}
            report.open_delegations.append(item)
            if launched:
                report.blockers.append(f"delegation {item['id']} is {state} and was launched; finish or cancel "
                                       "it under Spec Guard first (D12)")
            elif not item["acknowledged"]:
                report.blockers.append(f"delegation {item['id']} is {state} and never launched; acknowledge it with "
                                       f"--acknowledge-stale {item['id']} if it is dead (D12)")


def _private_dir(path: Path) -> None:
    """Create `path` and any missing parents owner-only, and make `path` itself 0700: mkdir(parents=True) gives the
    parents the umask's mode (0755), and backups hold full mailbox copies."""
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    path.chmod(0o700)


def _private_tree(root: Path) -> None:
    """Make a copied tree owner-only: directories 0700, files 0600 (symlinks are left as they are)."""
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            continue
        path.chmod(0o700 if path.is_dir() else 0o600)


def _sqlite_copy(source: Path, target: Path) -> None:
    with _read_only(source) as reader, sqlite3.connect(target) as writer:
        reader.backup(writer)
    target.chmod(0o600)


def _file_copy(source: Path, target: Path) -> None:
    shutil.copy2(source, target)
    target.chmod(0o600)


class MigrationBusy(Exception):
    """Another state migration holds the lock (D116)."""


@contextmanager
def _exclusive(parent: Path) -> Iterator[None]:
    """Hold an exclusive flock on the state root directory itself for the whole call (D116): no lock file is
    written, and the kernel drops the lock if the process dies."""
    descriptor = os.open(parent, os.O_RDONLY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise MigrationBusy("another state migration is running") from error
        yield
    finally:
        os.close(descriptor)


def migrate(home: Path, acknowledged: tuple[str, ...] = (),
            process_count: Callable[[Path], int] = _running_servers, *,
            target: Path | None = None, target_count: Callable[[Path], int] | None = None) -> tuple[Report, dict]:
    parent = _paths(home, target)["parent"]
    if not parent.is_dir():  # no agent-relay state root yet: inspect blocks (the runtime cannot be ready)
        report = inspect(home, acknowledged, process_count, target=target, target_count=target_count)
        return report, {"state": "blocked"}
    try:
        with _exclusive(parent):
            return _migrate(home, acknowledged, process_count, target, target_count)
    except MigrationBusy as error:
        return inspect(home, acknowledged, process_count, target=target, target_count=target_count), {
            "state": "blocked", "diagnostic": str(error)}


def _migrate(home: Path, acknowledged: tuple[str, ...], process_count: Callable[[Path], int],
             target: Path | None, target_count: Callable[[Path], int] | None) -> tuple[Report, dict]:
    report = inspect(home, acknowledged, process_count, target=target, target_count=target_count)
    if report.blockers:
        return report, {"state": "blocked"}
    paths = _paths(home, target)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = paths["backups"] / stamp
    if backup.exists():
        return report, {"state": "blocked", "diagnostic": f"backup {backup.name} already exists"}
    _private_dir(paths["parent"])
    _private_dir(paths["backups"])
    _private_dir(backup)
    stage = paths["parent"] / f"{STAGE_PREFIX}{stamp}-{secrets.token_hex(3)}"
    result: dict = {"state": "migrated", "backup": str(backup), "mismatches": []}
    try:
        _write_backup(paths, report, backup)
        stage.mkdir(mode=0o700)  # never exist_ok: a stage is ours once this returns (D118)
        items, expected = _prepare(paths, report, backup, stage)
    except Exception as error:  # nothing in the target was touched yet
        shutil.rmtree(stage, ignore_errors=True)
        return report, {**result, "state": "rolled-back", "diagnostic": f"preparing failed ({error}); the target "
                        "was not changed"}
    for name, counts in expected.items():
        staged = counts.pop("_staged")
        if staged != counts:
            result["mismatches"].append({"database": name, "expected": counts, "actual": staged})
    if result["mismatches"]:
        shutil.rmtree(stage, ignore_errors=True)
        return report, {**result, "state": "rolled-back", "diagnostic": "the prepared copy does not match the backup"}
    journal = {"stamp": stamp, "stage": str(stage), "backup": str(backup), "items": items, "counts": expected,
               "step": None}
    journalled = False
    try:
        for item in items:
            name, target_path = item["name"], Path(item["target"])
            journal["step"] = f"{name}:retiring"
            journalled = True  # from here a journal may exist, even if this write fails half way
            _write_journal(paths["parent"], journal)
            if target_path.exists():
                target_path.rename(stage / f"previous-{name}")
            journal["step"] = f"{name}:placing"
            _write_journal(paths["parent"], journal)
            (stage / name).rename(target_path)
        journal["step"] = "verifying"
        _write_journal(paths["parent"], journal)
        result["mismatches"] = _verify(paths, items, expected, result)
        if result["mismatches"]:
            raise MigrationMismatch("the row counts or the runtime differ after the swap")
    except Exception as error:
        if not journalled:
            shutil.rmtree(stage, ignore_errors=True)
            return report, {**result, "state": "rolled-back", "diagnostic": f"{error}; the target was not changed"}
        kept = _put_back(paths["parent"], journal)
        return report, {**result, "state": "rolled-back", "kept": str(kept),
                        "diagnostic": f"{error}; the target was put back as it was"}
    _journal_file(paths["parent"]).unlink()
    result["previous"] = str(stage)
    return report, result


class MigrationMismatch(Exception):
    """The swapped target does not match what was prepared (D119)."""


def _journal_file(parent: Path) -> Path:
    return parent / JOURNAL_NAME


def _write_journal(parent: Path, journal: dict) -> None:
    _runtime.write_private_json(_journal_file(parent), journal)


def _write_backup(paths: dict[str, Path], report: Report, backup: Path) -> None:
    """The timestamped backup, as before: snapshots of the old databases, daily backups and data."""
    old_mailbox = paths["old_runtime"] / "mailbox"
    if report.old_mailbox is not None:
        # Snapshot once into the backup, then build the target from the backup, so both hold the same data.
        _private_dir(backup / "mailbox" / "backups")
        with tempfile.TemporaryDirectory(prefix="agent-relay-migrate-") as scratch:
            _sqlite_copy(_snapshot(old_mailbox / "bridge.sqlite", Path(scratch)), backup / "mailbox" / "bridge.sqlite")
        for daily in sorted((old_mailbox / "backups").glob("*")):
            if daily.is_file():
                _file_copy(daily, backup / "mailbox" / "backups" / daily.name)
        if (paths["old_runtime"] / "data").is_dir():
            shutil.copytree(paths["old_runtime"] / "data", backup / "data")
            _private_tree(backup / "data")  # copytree keeps the source modes
    if report.old_delegation is not None:
        with tempfile.TemporaryDirectory(prefix="agent-relay-migrate-") as scratch:
            _sqlite_copy(_snapshot(paths["old_delegation"], Path(scratch)), backup / DATABASE_FILENAME)


def _start_from(current: Path, staged: Path, skip: tuple[str, ...] = ()) -> None:
    """Begin a staged directory as a copy of the current target (minus `skip` at its top), or empty and private."""
    if current.is_dir():
        shutil.copytree(current, staged, symlinks=True,
                        ignore=lambda directory, names: [n for n in names if Path(directory) == current and n in skip])
    else:
        staged.mkdir(mode=0o700)
    staged.chmod(0o700)


def _prepare(paths: dict[str, Path], report: Report, backup: Path, stage: Path) -> tuple[list[dict], dict]:
    """Build every directory the swap will place, next to the target (D118); return the items and the counts."""
    items: list[dict] = []
    expected: dict[str, dict] = {}

    def item(name: str, target_path: Path) -> None:
        items.append({"name": name, "target": str(target_path), "existed": target_path.exists()})

    if report.old_mailbox is not None:
        current = paths["runtime"] / "mailbox"
        staged = stage / "mailbox"
        _start_from(current, staged, ("bridge.sqlite", "bridge.sqlite-wal", "bridge.sqlite-shm"))
        _private_dir(staged / "backups")
        for daily in sorted((backup / "mailbox" / "backups").glob("*")):
            _file_copy(daily, staged / "backups" / daily.name)
        _sqlite_copy(backup / "mailbox" / "bridge.sqlite", staged / "bridge.sqlite")
        expected["mailbox"] = {**table_counts(backup / "mailbox" / "bridge.sqlite"),
                               "_staged": table_counts(staged / "bridge.sqlite")}
        item("mailbox", current)
        if (backup / "data").is_dir():
            current = paths["runtime"] / "data"
            _start_from(current, stage / "data")
            shutil.copytree(backup / "data", stage / "data", dirs_exist_ok=True, symlinks=True)
            (stage / "data").chmod(0o700)  # the runtime requires 0700
            item("data", current)
    if report.old_delegation is not None:
        current = paths["delegation"]
        staged = stage / "delegation"
        _start_from(current, staged)
        _sqlite_copy(backup / DATABASE_FILENAME, staged / DATABASE_FILENAME)
        expected["delegation"] = {**table_counts(backup / DATABASE_FILENAME),
                                  "_staged": table_counts(staged / DATABASE_FILENAME)}
        DelegationStore(staged)  # refuses a database it cannot use, before anything is swapped
        item("delegation", current)
    return items, expected


def _verify(paths: dict[str, Path], items: list[dict], expected: dict, result: dict) -> list[dict]:
    mismatches = []
    placed = {item["name"]: Path(item["target"]) for item in items}
    for name, database in (("mailbox", "bridge.sqlite"), ("delegation", DATABASE_FILENAME)):
        if name in placed:
            actual = table_counts(placed[name] / database)
            result[name] = actual
            if actual != expected[name]:
                mismatches.append({"database": name, "expected": expected[name], "actual": actual})
    after = runtime_status(paths["runtime"])
    if after.get("state") != "ready":
        mismatches.append({"runtime": after})
    return mismatches


def _put_back(parent: Path, journal: dict) -> Path:
    """Undo a journalled swap, newest item first (D119): what was placed goes back into the stage, what was retired
    returns to its place. Back only, never forward. The journal goes, the stage is kept as a failed one."""
    stage = Path(journal["stage"])
    for entry in reversed(journal["items"]):
        name, target_path = entry["name"], Path(entry["target"])
        staged, previous = stage / name, stage / f"previous-{name}"
        if not staged.exists() and target_path.exists():
            target_path.rename(staged)
        if previous.exists():
            previous.rename(target_path)
    _journal_file(parent).unlink(missing_ok=True)
    kept = stage.with_name(stage.name.replace(STAGE_PREFIX, FAILED_PREFIX, 1))
    stage.rename(kept)
    return kept


def host_next_steps(report: Report) -> list[str]:
    steps = []
    if not report.hosts.get("claude_new") or not report.hosts.get("codex_new"):
        steps.append("Attach the new host entries with the collaboration-ops skill (install-claude / install-codex).")
    if report.hosts.get("claude_old") or report.hosts.get("codex_old"):
        steps.append("After the new entries work, remove the old entries with Spec Guard's own uninstall "
                     "(it installed them and removes them by exact match).")
    steps.append("Rename project allow rules from mcp__spec-guard-native-collaboration__bridge_* to "
                 "mcp__agent-relay__bridge_* by hand; agent-relay never edits permission files.")
    steps.append("~/.spec-guard/native-collaboration and ~/.spec-guard/session-delegation were not changed; remove "
                 "them yourself once you are satisfied (the backup above holds their data).")
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("detect", "migrate"))
    parser.add_argument("--confirm", action="store_true", help="required for migrate")
    parser.add_argument("--acknowledge-stale", action="append", default=[], metavar="ID_PREFIX",
                        help="a never-launched, non-terminal delegation the user confirms is dead (D12)")
    parser.add_argument("--home", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    home = args.home or Path.home()
    try:
        # A test-only --home keeps `<home>/.agent-relay`; otherwise the state root (D21).
        target = None if args.home is not None else default_target()
    except StateHomeError as error:
        parser.exit(2, f"{parser.prog}: error: {error}\n")
    if any(not re.fullmatch(r"[0-9a-f-]{6,36}", prefix) for prefix in args.acknowledge_stale):
        parser.error("--acknowledge-stale takes a delegation id prefix of at least six hex characters")
    acknowledged = tuple(args.acknowledge_stale)
    if args.command == "detect":
        report = inspect(home, acknowledged, target=target)
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        return 0
    if not args.confirm:
        parser.error("migrate needs --confirm")
    report, result = migrate(home, acknowledged, target=target)
    output = {"report": report.as_dict(), "result": result}
    if result["state"] == "migrated":
        output["next_steps"] = host_next_steps(report)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if result["state"] == "migrated" else 1


if __name__ == "__main__":
    sys.exit(main())
