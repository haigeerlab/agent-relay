"""Read-only mailbox opens work on every supported Python's SQLite (round2-fixes D51, round 2 finding R2-9).

macOS's /usr/bin/python3 3.9 ships SQLite 3.43, whose `mode=ro` cannot open a WAL-mode file that has no -wal or -shm
beside it: the shape of a mailbox no bridge has open, and of the copy SQLite's backup API writes.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from native_collaboration_doctor import doctor
from native_collaboration_retire import identity_state
from native_collaboration_runtime import _mailbox_counts, install_runtime, open_mailbox_read_only, uninstall_runtime
from session_delegation_backend import native_registration_probe
from test_runtime_upgrade import fake_run


def closed_wal_mailbox(database: Path) -> None:
    """A schema-5 WAL-mode mailbox with every row checkpointed and no -wal/-shm left beside it."""
    with contextlib.closing(sqlite3.connect(database)) as connection:
        connection.executescript("""
            PRAGMA journal_mode = WAL;
            PRAGMA user_version = 5;
            CREATE TABLE agents (name TEXT PRIMARY KEY, registered_at TEXT, retired_at TEXT);
            CREATE TABLE messages (id INTEGER PRIMARY KEY, from_agent TEXT, to_agent TEXT, body TEXT, created_at TEXT);
            CREATE TABLE acknowledgements (message_id INTEGER, agent TEXT);
            CREATE TABLE wake_jobs (id INTEGER PRIMARY KEY, state TEXT);
            CREATE TABLE wake_targets (agent TEXT PRIMARY KEY, target TEXT);
            INSERT INTO agents VALUES ('a', '2026-10-07T00:00:00Z', NULL);
            INSERT INTO messages VALUES (1, 'b', 'a', 'one', '2026-10-07T00:00:01Z'), (2, 'b', 'a', 'two', '2026-10-07T00:00:02Z');
        """)
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for suffix in ("-wal", "-shm"):  # Apple's SQLite keeps them after close; a stopped bridge's node:sqlite does not
        Path(str(database) + suffix).unlink(missing_ok=True)
    database.chmod(0o600)


def side_files(database: Path) -> list[str]:
    return sorted(path.name for path in database.parent.iterdir() if path.name != database.name)


class MailboxReadOnlyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-ro-")
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.database = self.base / "mailbox" / "bridge.sqlite"
        self.database.parent.mkdir(mode=0o700)
        closed_wal_mailbox(self.database)

    def test_the_shared_opener_reads_a_closed_wal_mailbox_and_leaves_nothing_beside_it(self):
        with contextlib.closing(open_mailbox_read_only(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)
        self.assertEqual(side_files(self.database), [])

    def test_the_shared_opener_still_sees_rows_only_in_the_wal(self):
        with contextlib.closing(sqlite3.connect(self.database)) as writer:
            writer.execute("PRAGMA wal_autocheckpoint = 0")
            writer.execute("INSERT INTO messages VALUES (3, 'b', 'a', 'three', 'x')")
            writer.commit()
            with contextlib.closing(open_mailbox_read_only(self.database)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 3)

    def test_the_shared_opener_never_writes(self):
        with contextlib.closing(open_mailbox_read_only(self.database)) as connection, \
                self.assertRaises(sqlite3.OperationalError):
            connection.execute("INSERT INTO messages VALUES (9, 'b', 'a', 'x', 'x')")

    def test_reinstall_counts_a_closed_wal_mailbox(self):
        self.assertEqual(_mailbox_counts(self.database), {"agents": 1, "messages": 2, "acknowledgements": 0,
                                                          "wake_jobs": 0})
        self.assertEqual(side_files(self.database), [])

    def test_retire_and_the_delegation_probe_read_a_closed_wal_mailbox(self):
        self.assertEqual(identity_state(self.database, "a"), {"state": "active", "unacknowledged": 2})
        self.assertIs(native_registration_probe(self.database)("a", None, "s", "bounded-development"), True)

    def test_doctor_reads_a_closed_wal_mailbox(self):
        root = self.base / "runtime"
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            install_runtime(root)
        (root / "mailbox" / "bridge.sqlite").unlink(missing_ok=True)
        closed_wal_mailbox(root / "mailbox" / "bridge.sqlite")
        report = doctor(root, home=self.base, probe=lambda _r: {"state": "ready", "toolCount": 17},
                        processes=lambda: [], alive=lambda _pid: False)
        mailbox = next(check for check in report["checks"] if check["check"] == "mailbox")
        self.assertEqual(mailbox["state"], "ok", mailbox)

    def test_install_rebuilds_around_a_closed_wal_mailbox(self):
        root = self.base / "runtime"
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            install_runtime(root)
        (root / "mailbox" / "bridge.sqlite").unlink(missing_ok=True)
        closed_wal_mailbox(root / "mailbox" / "bridge.sqlite")
        history = (root / "mailbox" / "bridge.sqlite").read_bytes()
        uninstall_runtime(root, running=lambda _root: 0)
        with patch("native_collaboration_runtime.subprocess.run", side_effect=fake_run):
            self.assertEqual(install_runtime(root)["state"], "ready")
        self.assertEqual((root / "mailbox" / "bridge.sqlite").read_bytes(), history)


if __name__ == "__main__":
    unittest.main()
