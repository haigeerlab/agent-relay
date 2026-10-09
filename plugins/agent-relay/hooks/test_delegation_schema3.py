#!/usr/bin/env python3
"""delegation-continue-parity D172: the delegation store's schema 3 (scope and state_reason) and its 2 -> 3 migration."""
from __future__ import annotations

import sqlite3
import stat
import unittest
from unittest.mock import patch

import session_delegation
from session_delegation import DelegationError, DelegationStore
from test_session_delegation import NOW, DelegationTestCase

ENVELOPE = "11111111-1111-4111-8111-111111111111"
DELEGATION = "22222222-2222-4222-8222-222222222222"

# The schema 0.6.0 created (user_version 2), verbatim.
SCHEMA_TWO = (
    """CREATE TABLE authorizations (
    envelope_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, request_digest TEXT NOT NULL,
    horizon TEXT NOT NULL, origin_host TEXT NOT NULL, origin_session TEXT NOT NULL, project_root TEXT NOT NULL,
    repo_identity TEXT NOT NULL, baseline TEXT NOT NULL, dirty INTEGER NOT NULL, target_hosts TEXT NOT NULL,
    permission_intent TEXT NOT NULL, host_permission TEXT, max_sessions INTEGER NOT NULL, expires_at INTEGER NOT NULL,
    depth INTEGER NOT NULL, summary TEXT NOT NULL, state TEXT NOT NULL, created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL)""",
    """CREATE TABLE delegations (
    delegation_id TEXT PRIMARY KEY, envelope_id TEXT NOT NULL REFERENCES authorizations(envelope_id),
    launch_key TEXT NOT NULL UNIQUE, target_host TEXT NOT NULL, permission_intent TEXT NOT NULL,
    friendly_name TEXT NOT NULL, state TEXT NOT NULL, host_ref TEXT, host_session_ref TEXT, host_version TEXT,
    actual_permission TEXT, last_turn_ref TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""",
)


class SchemaThreeTests(DelegationTestCase):
    def schema_two_store(self):
        """A store as 0.6.0 left it: one completed Claude review."""
        self.root.mkdir(mode=0o700)
        database = self.root / "delegation.sqlite"
        with sqlite3.connect(database) as connection:
            for statement in SCHEMA_TWO:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO authorizations VALUES (?, 'request-12345678', 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff', 'task', 'codex', 'origin', ?, "
                "'git:example/project', ?, 0, '[\"claude\"]', 'safe-review', NULL, 1, ?, 0, 'Review', 'authorized', "
                "?, ?)", (ENVELOPE, str(self.project.resolve()), "a" * 40, NOW + 600, NOW, NOW))
            connection.execute(
                "INSERT INTO delegations VALUES (?, ?, 'launch-12345678', 'claude', 'safe-review', 'pwa-cc', "
                "'completed', 'bg-1', 'session-1', '2.1.295', 'dontAsk/safe-review', 'turn-1', ?, ?)",
                (DELEGATION, ENVELOPE, NOW, NOW))
            connection.execute("PRAGMA user_version = 2")
        database.chmod(0o600)
        return database

    @staticmethod
    def version(path):
        with sqlite3.connect(path) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_a_schema_two_store_migrates_in_place_and_keeps_a_copy(self):
        database = self.schema_two_store()
        store = self.store()
        self.assertEqual(self.version(database), 3)
        claim = store.get_delegation(DELEGATION)
        self.assertEqual((claim.state, claim.friendly_name, claim.host_session_ref), ("completed", "pwa-cc", "session-1"))
        self.assertIsNone(claim.scope, "a record from before schema 3 has an unknown scope")
        self.assertIsNone(claim.state_reason)
        copy = self.root / session_delegation.SCHEMA_TWO_COPY
        self.assertEqual(stat.S_IMODE(copy.stat().st_mode), 0o600)
        self.assertEqual(self.version(copy), 2)
        with sqlite3.connect(copy) as connection:
            self.assertEqual(connection.execute("SELECT friendly_name FROM delegations").fetchall(), [("pwa-cc",)])
        before = copy.stat().st_mtime_ns
        self.store()
        self.assertEqual(copy.stat().st_mtime_ns, before, "a second open is a no-op")
        self.assertEqual(self.version(database), 3)

    def test_an_interrupted_migration_leaves_schema_two_and_reruns(self):
        database = self.schema_two_store()
        original = session_delegation._add_schema_three_columns

        def crash(connection):
            original(connection)
            raise sqlite3.OperationalError("killed")

        with patch.object(session_delegation, "_add_schema_three_columns", crash):
            with self.assertRaises(DelegationError):
                self.store()
        self.assertEqual(self.version(database), 2)
        with sqlite3.connect(database) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(delegations)")}
        self.assertNotIn("scope", columns, "the failed migration rolled back")
        self.assertEqual(self.store().get_delegation(DELEGATION).state, "completed")
        self.assertEqual(self.version(database), 3)

    def test_a_new_store_is_schema_three_and_stores_the_scope(self):
        store = self.store()
        self.assertEqual(self.version(store.database), session_delegation.SCHEMA_VERSION)
        self.assertEqual(session_delegation.SCHEMA_VERSION, 3)
        self.assertFalse((self.root / session_delegation.SCHEMA_TWO_COPY).exists())
        envelope = self.authorize(store, max_sessions=2, horizon="batch")
        scoped = store.claim_launch(envelope.envelope_id, "launch-scoped-1", "claude", self.project, "a" * 40,
                                    "safe-review", scope=("README.md", "docs"))
        plain = store.claim_launch(envelope.envelope_id, "launch-plain-1", "claude", self.project, "a" * 40,
                                   "safe-review")
        self.assertEqual(store.get_delegation(scoped.delegation_id).scope, ("README.md", "docs"))
        self.assertEqual(store.get_delegation(plain.delegation_id).scope, ())

    def test_a_retried_held_create_takes_the_scope_of_the_retry(self):
        store = self.store()
        envelope = self.authorize(store)
        first = store.claim_launch(envelope.envelope_id, "launch-retry-1", "claude", self.project, "a" * 40,
                                   "safe-review", scope=("README.md",))
        again = store.claim_launch(envelope.envelope_id, "launch-retry-1", "claude", self.project, "a" * 40,
                                   "safe-review", scope=("docs",))
        self.assertEqual(again.delegation_id, first.delegation_id)
        self.assertEqual(store.get_delegation(first.delegation_id).scope, ("docs",))

    def test_every_state_change_records_its_reason(self):
        clock = [NOW]
        store = DelegationStore(self.root, now=lambda: clock[0])
        envelope = self.authorize(store, max_sessions=2, horizon="batch")
        claim = store.claim_launch(envelope.envelope_id, "launch-reason-1", "claude", self.project, "a" * 40,
                                   "safe-review")
        self.assertIsNone(claim.state_reason)
        self.assertEqual(store.record_host_unknown(claim.delegation_id).state_reason, "host-result-unknown")
        self.assertEqual(store.bind_host(claim.delegation_id, "bg-1", "session-1", "2.1.295",
                                         "dontAsk/safe-review").state_reason, "host-created")
        self.assertEqual(store.advance(claim.delegation_id, "cancelled", "host-cancelled").state_reason,
                         "host-cancelled")
        stuck = store.claim_launch(envelope.envelope_id, "launch-reason-2", "claude", self.project, "a" * 40,
                                   "safe-review")
        clock[0] += store.STALE_AFTER_SECONDS
        self.assertEqual(store.prune_stale(stuck.delegation_id).state_reason, "pruned-stale")

    def test_a_malformed_scope_is_invalid_contents(self):
        store = self.store()
        envelope = self.authorize(store)
        claim = store.claim_launch(envelope.envelope_id, "launch-bad-1", "claude", self.project, "a" * 40,
                                   "safe-review")
        with sqlite3.connect(store.database) as connection:
            connection.execute("UPDATE delegations SET scope = '{\"x\": 1}' WHERE delegation_id = ?",
                               (claim.delegation_id,))
        with self.assertRaisesRegex(DelegationError, "contents are invalid"):
            self.store()


if __name__ == "__main__":
    unittest.main()
