"""Mailbox readers wait for a bridge's write lock instead of failing at once (identity-check D40)."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from native_collaboration_retire import _open_read_only
from native_collaboration_runtime import MAILBOX_BUSY_TIMEOUT
from session_delegation_backend import _mailbox_connection


class MailboxBusyTimeoutTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-busy-")
        self.addCleanup(tmp.cleanup)
        self.database = Path(tmp.name) / "bridge.sqlite"
        with sqlite3.connect(self.database) as connection:
            connection.executescript("PRAGMA journal_mode = WAL; CREATE TABLE t (x); INSERT INTO t VALUES (1);")
        self.database.chmod(0o600)

    def hold(self, seconds):
        locked = threading.Event()

        def run():
            connection = sqlite3.connect(self.database, isolation_level=None)
            connection.executescript("PRAGMA locking_mode = EXCLUSIVE; BEGIN EXCLUSIVE; SELECT * FROM t;")
            locked.set()
            time.sleep(seconds)
            connection.execute("COMMIT")
            connection.close()

        thread = threading.Thread(target=run)
        thread.start()
        locked.wait(5)
        self.addCleanup(thread.join)

    def test_the_timeout_is_the_bridge_busy_timeout(self):
        self.assertEqual(MAILBOX_BUSY_TIMEOUT, 5.0)

    def test_both_readers_wait_for_a_held_lock(self):
        for opener in (_open_read_only, _mailbox_connection):
            with self.subTest(opener=opener.__name__):
                self.hold(0.6)
                started = time.monotonic()
                connection = opener(self.database)
                try:
                    self.assertEqual(connection.execute("SELECT x FROM t").fetchone()[0], 1)
                finally:
                    connection.close()
                self.assertGreaterEqual(time.monotonic() - started, 0.4)


if __name__ == "__main__":
    unittest.main()
