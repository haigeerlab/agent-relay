#!/usr/bin/env python3
"""State migration: blockers stop before any write; a migration copies, verifies, and leaves old data untouched."""
import hashlib
import json
import sqlite3
import stat
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import state_migration
from native_collaboration_runtime import BRIDGE_COMMIT, status
from session_delegation import DelegationStore


ENVELOPE = "11111111-2222-4333-8444-555555555555"


def no_servers(_path):
    return 0


def tree_digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="ar-migration-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.old_runtime = self.home / ".spec-guard" / "native-collaboration"
        self.old_delegation_dir = self.home / ".spec-guard" / "session-delegation"
        self.runtime = self.home / ".agent-relay" / "runtime"

    def private(self, path):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)

    def make_old_mailbox(self, messages=3, agents=2):
        mailbox = self.old_runtime / "mailbox"
        self.private(mailbox / "backups")
        self.private(self.old_runtime / "data" / "claude-codex-bridge" / "runs")
        (self.old_runtime / "data").chmod(0o755)  # a looser source mode must not loosen the target
        database = mailbox / "bridge.sqlite"
        with sqlite3.connect(database) as connection:
            connection.executescript(
                "PRAGMA journal_mode=WAL;"
                "CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT);"
                "CREATE TABLE acknowledgements (message_id INTEGER);"
                "CREATE TABLE agents (name TEXT PRIMARY KEY);"
                "CREATE TABLE wake_jobs (id INTEGER PRIMARY KEY, state TEXT);"
                "CREATE TABLE meta (key TEXT);")
            connection.executemany("INSERT INTO messages (body) VALUES (?)", [("x",)] * messages)
            connection.executemany("INSERT INTO acknowledgements VALUES (?)", [(i,) for i in range(messages)])
            connection.executemany("INSERT INTO agents VALUES (?)", [(f"a{i}",) for i in range(agents)])
            connection.executemany("INSERT INTO wake_jobs (state) VALUES (?)",
                                   [("read",), ("unknown",), ("accepted",), ("cancelled",)])
            connection.execute("INSERT INTO meta VALUES ('v')")
        database.chmod(0o600)
        daily = mailbox / "backups" / "bridge-daily-2026-10-06.sqlite"
        daily.write_bytes(b"daily")
        daily.chmod(0o600)

    def make_old_delegation(self, rows=(("cancelled", None),)):
        DelegationStore(self.old_delegation_dir)
        database = self.old_delegation_dir / "delegation.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "INSERT INTO authorizations VALUES (?, 'key-00000001', ?, 'task', 'claude', 'origin', '/p', 'repo', "
                "'base', 0, '[\"codex\"]', 'safe-review', NULL, 1, 9999999999, 0, 'summary', 'cancelled', 1, 1)",
                (ENVELOPE, "0" * 64))
            for index, (state, host_session) in enumerate(rows):
                connection.execute(
                    "INSERT INTO delegations VALUES (?, ?, ?, 'codex', 'safe-review', 'name', ?, NULL, ?, NULL, "
                    "NULL, NULL, 1, 1)",
                    (f"{index:02d}f0de1b-0d71-4068-b6f5-f17af11bd8ce", ENVELOPE, f"launch-{index:08d}", state,
                     host_session))

    def make_ready_runtime(self, agents=0):
        for directory in (self.runtime, self.runtime / "mailbox", self.runtime / "mailbox" / "backups",
                          self.runtime / "data"):
            self.private(directory)
        (self.runtime / "dist").mkdir()
        (self.runtime / "dist" / "server.js").write_text("server\n", encoding="utf-8")
        (self.runtime / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}), encoding="utf-8")
        if agents:
            database = self.runtime / "mailbox" / "bridge.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE agents (name TEXT)")
                connection.executemany("INSERT INTO agents VALUES (?)", [("x",)] * agents)
            database.chmod(0o600)
        self.assertEqual(status(self.runtime)["state"], "ready")

    def make_ready_case(self):
        self.make_old_mailbox()
        self.make_old_delegation()
        self.make_ready_runtime()


class DetectTests(Fixture):
    def test_reports_counts_open_work_and_writes_nothing(self):
        self.make_old_mailbox()
        self.make_old_delegation(rows=(("cancelled", None), ("creating", None)))
        before = tree_digest(self.home)
        report = state_migration.inspect(self.home, process_count=no_servers)
        self.assertEqual(tree_digest(self.home), before)
        self.assertEqual(report.old_mailbox["messages"], 3)
        self.assertEqual(report.old_mailbox["agents"], 2)
        self.assertEqual(report.old_delegation, {"authorizations": 1, "delegations": 2})
        self.assertEqual(report.wake_jobs, {"accepted": 1, "unknown": 1})
        self.assertEqual(report.open_delegations,
                         [{"id": "01f0de", "state": "creating", "launched": False, "acknowledged": False}])
        self.assertFalse((self.home / ".agent-relay").exists())

    def test_reports_host_entries_by_presence_only(self):
        (self.home / ".claude.json").write_text(json.dumps({"mcpServers": {"spec-guard-native-collaboration": {}}}))
        (self.home / ".codex").mkdir()
        (self.home / ".codex" / "config.toml").write_text("[mcp_servers.agent_relay]\ncommand = \"node\"\n")
        hosts = state_migration.inspect(self.home, process_count=no_servers).hosts
        self.assertEqual(hosts, {"claude_old": True, "claude_new": False, "codex_old": False, "codex_new": True})


class BlockerTests(Fixture):
    def assert_blocked(self, needle, acknowledged=(), process_count=no_servers):
        before = tree_digest(self.home)
        report, result = state_migration.migrate(self.home, acknowledged, process_count)
        self.assertEqual(result["state"], "blocked")
        self.assertTrue(any(needle in blocker for blocker in report.blockers), report.blockers)
        self.assertEqual(tree_digest(self.home), before)
        self.assertFalse((self.home / ".agent-relay" / "backups").exists())

    def test_a_launched_open_delegation_always_blocks(self):
        self.make_ready_case()
        with sqlite3.connect(self.old_delegation_dir / "delegation.sqlite") as connection:
            connection.execute("UPDATE delegations SET state='running', host_session_ref='s'")
        self.assert_blocked("was launched", acknowledged=("00f0de",))

    def test_a_stale_never_launched_delegation_blocks_until_acknowledged(self):
        self.make_old_mailbox()
        self.make_old_delegation(rows=(("creating", None),))
        self.make_ready_runtime()
        self.assert_blocked("never launched")
        report = state_migration.inspect(self.home, ("00f0de",), no_servers)
        self.assertEqual(report.blockers, [])

    def test_running_old_servers_block(self):
        self.make_ready_case()
        self.assert_blocked("2 old bridge server", process_count=lambda _path: 2)

    def test_target_runtime_must_be_ready(self):
        self.make_old_mailbox()
        self.make_old_delegation()
        self.assert_blocked("runtime is not ready")

    def test_a_used_target_mailbox_is_never_merged(self):
        self.make_old_mailbox()
        self.make_old_delegation()
        self.make_ready_runtime(agents=1)
        self.assert_blocked("never merged")

    def test_an_existing_target_delegation_database_is_never_merged(self):
        self.make_ready_case()
        DelegationStore(self.home / ".agent-relay" / "delegation")
        self.assert_blocked("delegation database already exists")

    def test_nothing_to_migrate_is_a_blocker(self):
        self.make_ready_runtime()
        self.assert_blocked("nothing to migrate")


class MigrateTests(Fixture):
    def test_copies_verifies_and_leaves_old_data_untouched(self):
        self.make_ready_case()
        old_before = tree_digest(self.home / ".spec-guard")
        report, result = state_migration.migrate(self.home, (), no_servers)
        self.assertEqual(result["state"], "migrated", result)
        self.assertEqual(tree_digest(self.home / ".spec-guard"), old_before)
        self.assertEqual(result["mailbox"], report.old_mailbox)
        self.assertEqual(result["delegation"], report.old_delegation)
        target = self.runtime / "mailbox" / "bridge.sqlite"
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertTrue((self.runtime / "mailbox" / "backups" / "bridge-daily-2026-10-06.sqlite").is_file())
        self.assertTrue((self.runtime / "data" / "claude-codex-bridge" / "runs").is_dir())
        self.assertEqual(status(self.runtime)["state"], "ready")
        delegation = self.home / ".agent-relay" / "delegation"
        self.assertEqual(stat.S_IMODE(delegation.stat().st_mode), 0o700)
        DelegationStore(delegation)
        backup = Path(result["backup"])
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        for name in ("mailbox/bridge.sqlite", "mailbox/backups/bridge-daily-2026-10-06.sqlite", "delegation.sqlite"):
            self.assertTrue((backup / name).is_file(), name)
        self.assertEqual(state_migration.table_counts(backup / "mailbox" / "bridge.sqlite"), report.old_mailbox)

    def test_a_count_mismatch_is_reported_and_nothing_is_removed(self):
        self.make_ready_case()
        old_before = tree_digest(self.home / ".spec-guard")
        real = state_migration.table_counts

        def skewed(path):
            counts = real(path)
            if path == self.runtime / "mailbox" / "bridge.sqlite":
                counts["messages"] -= 1
            return counts

        with mock.patch.object(state_migration, "table_counts", side_effect=skewed):
            _report, result = state_migration.migrate(self.home, (), no_servers)
        self.assertEqual(result["state"], "verification-failed")
        self.assertEqual(result["mismatches"][0]["database"], "mailbox")
        self.assertTrue(Path(result["backup"]).is_dir())
        self.assertEqual(tree_digest(self.home / ".spec-guard"), old_before)


class CommandLineTests(Fixture):
    def test_migrate_requires_confirm_and_a_hex_prefix(self):
        for argv in (["migrate", "--home", str(self.home)],
                     ["detect", "--home", str(self.home), "--acknowledge-stale", "../x"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                state_migration.main(argv)
        self.assertFalse((self.home / ".agent-relay").exists())


    def test_every_backup_directory_is_private_whatever_the_umask(self):
        # 2026-10-07: intermediate directories (backups/, mailbox/) were created 0755 by mkdir(parents=True).
        self.make_ready_case()
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        backups = self.home / ".agent-relay" / "backups"
        backups.mkdir(parents=True)
        backups.chmod(0o755)
        _report, result = state_migration.migrate(self.home, (), no_servers)
        self.assertEqual(result["state"], "migrated", result)
        open_entries = [str(path) for path in [backups, *backups.rglob("*")]
                        if path.is_dir() and stat.S_IMODE(path.stat().st_mode) & 0o077]
        self.assertEqual(open_entries, [])


if __name__ == "__main__":
    unittest.main()
