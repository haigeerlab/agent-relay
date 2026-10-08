"""delegation-store-init: any number of processes may open a new delegation state root at once (D127, D128)."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

from session_delegation import DATABASE_FILENAME, DelegationError, DelegationStore

HOOKS = Path(__file__).resolve().parent


class StoreInitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ar-store-init-")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)

    def version(self, root):
        with sqlite3.connect(root / DATABASE_FILENAME) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_processes_opening_a_fresh_root_at_once_all_succeed(self):
        script = textwrap.dedent("""
            import os, sys, time
            from pathlib import Path
            sys.path.insert(0, sys.argv[1])
            from session_delegation import DelegationStore
            barrier = Path(sys.argv[3])
            while not barrier.exists():
                time.sleep(0.001)
            try:
                DelegationStore(Path(sys.argv[2]))
                print("ok")
            except Exception as error:
                print("ERR", error)
        """)
        failures = []
        for round_number in range(8):
            root = self.parent / f"state-{round_number}"
            barrier = self.parent / f"go-{round_number}"
            processes = [subprocess.Popen([sys.executable, "-B", "-c", script, str(HOOKS), str(root), str(barrier)],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                         for _ in range(4)]
            time.sleep(0.3)  # every process is waiting at the barrier
            barrier.write_text("", encoding="utf-8")
            for process in processes:
                out, err = process.communicate(timeout=60)
                if process.returncode != 0 or out.strip() != "ok":
                    failures.append((round_number, out.strip(), err.strip()[-200:]))
            if not failures:
                self.assertEqual(self.version(root), 2)
        self.assertEqual(failures, [])

    def test_an_empty_database_left_by_a_dead_creator_is_initialized(self):
        root = self.parent / "state"
        root.mkdir(mode=0o700)
        database = root / DATABASE_FILENAME
        os.close(os.open(database, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600))
        DelegationStore(root)
        self.assertEqual(self.version(root), 2)

    def test_a_foreign_database_at_version_0_is_still_refused(self):
        root = self.parent / "state"
        root.mkdir(mode=0o700)
        database = root / DATABASE_FILENAME
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE something_else (x)")
        database.chmod(0o600)
        with self.assertRaisesRegex(DelegationError, "schema is incomplete"):
            DelegationStore(root)
        with sqlite3.connect(database) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"something_else"}, "nothing was added to a foreign database")

    def missing_at_first(self, root):
        """Make the existence check miss `root` once, as when another process creates it right after the check."""
        real_exists, real_is_symlink = Path.exists, Path.is_symlink
        seen = {"exists": False, "is_symlink": False}

        def once(name, real):
            def check(path, *args, **kwargs):
                if path == root and not seen[name]:
                    seen[name] = True
                    return False
                return real(path, *args, **kwargs)
            return check
        return mock.patch.multiple(Path, exists=once("exists", real_exists),
                                   is_symlink=once("is_symlink", real_is_symlink))

    def test_a_directory_created_by_another_process_meanwhile_is_used(self):
        root = self.parent / "state"
        root.mkdir(mode=0o700)
        with self.missing_at_first(root):
            DelegationStore(root)
        self.assertEqual(self.version(root), 2)

    def test_a_symlink_created_meanwhile_is_still_refused(self):
        target = self.parent / "elsewhere"
        target.mkdir(mode=0o700)
        root = self.parent / "state"
        root.symlink_to(target)
        with self.missing_at_first(root), self.assertRaisesRegex(DelegationError, "symbolic link"):
            DelegationStore(root)


if __name__ == "__main__":
    unittest.main()
