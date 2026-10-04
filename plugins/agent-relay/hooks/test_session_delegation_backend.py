"""Native collaboration maps to one bounded host configuration."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from native_collaboration_adapters import CLAUDE_SERVER_NAME
from native_collaboration_runtime import BRIDGE_COMMIT
from session_delegation_backend import (
    BackendUnavailable,
    MailboxResultRoute,
    native_result_probe,
    native_result_route,
    resolve_backend,
)
from session_delegation_codex import COMMUNICATION_TOOLS, CommunicationServer


class DelegationBackendTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sg-delegation-backend-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.native = self.root / "native"
        for directory in (
            self.native, self.native / "dist", self.native / "mailbox",
            self.native / "mailbox" / "backups", self.native / "data",
        ):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.native / "manifest.json").write_text(
            json.dumps({"commit": BRIDGE_COMMIT}), encoding="utf-8")
        (self.native / "dist" / "server.js").write_text("server\n", encoding="utf-8")
        self.node = self.root / "node"
        self.node.write_text("fake\n", encoding="utf-8")
        self.node.chmod(0o700)

    def resolve(self):
        return resolve_backend(self.native, node=self.node)

    def test_resolves_only_native_mailbox(self):
        result = self.resolve()
        self.assertEqual(result.name, "native")
        self.assertIsInstance(result.codex_server, CommunicationServer)
        self.assertEqual(result.codex_server.command, self.node.resolve())
        self.assertEqual(result.codex_server.enabled_tools, COMMUNICATION_TOOLS)
        self.assertEqual(result.claude_tools, COMMUNICATION_TOOLS)
        self.assertEqual(result.claude_server_name, CLAUDE_SERVER_NAME)
        self.assertEqual(
            list(result.claude_config["mcpServers"]), [CLAUDE_SERVER_NAME])

    def test_missing_node_fails_without_an_alternate_transport(self):
        with self.assertRaisesRegex(BackendUnavailable, "node-unavailable"):
            resolve_backend(self.native, node=self.root / "missing-node")

    def _database(self) -> Path:
        database = self.native / "mailbox" / "bridge.sqlite"
        connection = sqlite3.connect(database)
        connection.executescript("""
            CREATE TABLE agents (
                name TEXT PRIMARY KEY, capabilities TEXT, registered_at TEXT,
                last_seen TEXT, retired_at TEXT);
            CREATE TABLE wake_targets (agent TEXT PRIMARY KEY, target TEXT);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY, from_agent TEXT, to_agent TEXT,
                body TEXT, thread_id TEXT, idempotency_key TEXT);
            PRAGMA user_version = 2;
        """)
        connection.execute(
            "INSERT INTO agents VALUES (?,?,?,?,NULL)",
            ("origin-codex", "[]", "now", "now"),
        )
        connection.execute(
            "INSERT INTO wake_targets VALUES (?,?)",
            ("origin-codex", json.dumps({
                "app": "codex", "sessionId": "origin-thread-exact",
            })),
        )
        connection.commit()
        connection.close()
        database.chmod(0o600)
        return database

    def test_registration_probe_checks_live_native_identity_and_wake_binding(self):
        database = self._database()
        probe = self.resolve().claude_registration_probe
        self.assertIsNotNone(probe)
        self.assertTrue(probe(
            "origin-codex", None, "origin-thread-exact", "bounded-development"))
        self.assertFalse(probe(
            "origin-codex", None, "origin-thread-exact", "safe-review"))
        database.chmod(0o644)
        self.assertIsNone(probe(
            "origin-codex", None, "origin-thread-exact", "bounded-development"))

    def test_result_route_requires_one_exact_live_origin_and_reads_only_metadata(self):
        database = self._database()
        route = native_result_route(
            database, "codex", "origin-thread-exact", "delegation-12345678")
        self.assertEqual(route, MailboxResultRoute(
            "native", "origin-codex", "spec-guard-result:delegation-12345678"))
        self.assertEqual(route.transport, "spec-guard-bridge")
        self.assertFalse(native_result_probe(database, route, "target-codex"))

        connection = sqlite3.connect(database)
        connection.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?)",
            (1, "target-codex", "origin-codex", "private result body",
             route.key, None),
        )
        connection.commit()
        connection.close()
        self.assertTrue(native_result_probe(database, route, "target-codex"))
        self.assertFalse(native_result_probe(database, route, "wrong-target"))


if __name__ == "__main__":
    unittest.main()
