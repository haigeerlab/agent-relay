"""Copy host configuration files before agent-relay writes them (safe-uninstall assumption 3).

The copies may hold credentials (MCP API keys, tokens), so every directory is made 0700 and every copy 0600 with
explicit modes, whatever the umask, and nothing here prints or logs file contents.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import stat
from typing import Sequence

from native_collaboration_runtime import StateHomeError, state_home

CREDENTIALS_NOTE = "it may contain credentials such as MCP API keys, so it stays owner-only"


class HostBackupError(Exception):
    """The backup could not be made; nothing may be written."""


def _private_dir(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, exist_ok=True)
        metadata = path.lstat()
    except OSError as error:
        raise HostBackupError(f"cannot create backup directory {path}: {error.strerror}") from error
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise HostBackupError(f"backup directory {path} is not an owner-owned directory")
    os.chmod(path, 0o700)


def _write_private(target: Path, data: bytes) -> None:
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def backup_host_files(paths: Sequence[Path]) -> Path:
    """Copy each existing file into ``$AGENT_RELAY_HOME/backups/<UTC>/host-config/``; list missing ones in
    ``missing.txt``. Return that directory. Raise HostBackupError on any failure, before anything is written."""
    try:
        home = state_home()
    except StateHomeError as error:
        raise HostBackupError(str(error)) from error
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        for directory in (home, home / "backups"):
            _private_dir(directory)
        for attempt in range(100):
            run = home / "backups" / (stamp if attempt == 0 else f"{stamp}-{attempt}")
            if not run.exists():
                break
        _private_dir(run)
        target = run / "host-config"
        _private_dir(target)
        missing: list[str] = []
        used: set[str] = set()
        for path in map(Path, paths):
            if not path.exists() and not path.is_symlink():
                missing.append(str(path))
                continue
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
                raise HostBackupError(f"{path} is not an owner-owned regular file, not backed up")
            name = path.name
            while name in used:
                name = "_" + name
            used.add(name)
            _write_private(target / name, path.read_bytes())
        if missing:
            _write_private(target / "missing.txt", "".join(item + "\n" for item in missing).encode())
    except OSError as error:
        raise HostBackupError(f"cannot back up host configuration: {error.strerror or error}") from error
    return target


def backup_message(target: Path) -> str:
    return f"Host configuration backed up to {target} ({CREDENTIALS_NOTE})."
