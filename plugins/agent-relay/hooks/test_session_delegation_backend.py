"""Selected collaboration backend maps to one bounded host configuration."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from collaboration_adapters import MCP_SERVER_NAME
from native_collaboration_adapters import CLAUDE_SERVER_NAME
from native_collaboration_runtime import BRIDGE_COMMIT
from session_delegation_backend import (
    BackendUnavailable,
    MailboxResultRoute,
    native_result_probe,
    native_result_route,
    resolve_backend,
    xats_result_probe,
    xats_result_route,
)
from session_delegation_codex import (
    COMMUNICATION_TOOLS,
    CommunicationServer,
    HttpCommunicationServer,
    XATS_COMMUNICATION_TOOLS,
)


class DelegationBackendTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sg-delegation-backend-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.xats = self.root / "xats"
        self.xats.mkdir(mode=0o700)
        (self.xats / "runtime.json").write_text(json.dumps({
            "host": "127.0.0.1", "port": 9100,
            "package": "cross-agent-teams-mcp", "packageVersion": "0.8.6",
            "tokenFile": "token",
        }), encoding="utf-8")
        (self.xats / "token").write_text("test-only-secret\n", encoding="utf-8")
        (self.xats / "token").chmod(0o600)
        self.native = self.root / "native"
        for directory in (
            self.native, self.native / "dist", self.native / "mailbox",
            self.native / "mailbox" / "backups", self.native / "data",
        ):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.native / "manifest.json").write_text(
            json.dumps({"commit": BRIDGE_COMMIT}), encoding="utf-8")
        (self.native / "dist" / "server.js").write_text("server\n", encoding="utf-8")
        self.node = self.executable("node")
        self.npx = self.executable("npx")
        self.python = self.executable("python3")
        self.header = self.file("collaboration_auth_header.py")
        self.stdio = self.file("collaboration_claude_stdio.py")
        self.marker = self.root / "transport.json"

    def executable(self, name):
        path = self.root / name
        path.write_text("fake\n", encoding="utf-8")
        path.chmod(0o700)
        return path

    def file(self, name):
        path = self.root / name
        path.write_text("fake\n", encoding="utf-8")
        return path

    def resolve(self):
        return resolve_backend(
            self.marker, self.native, self.xats,
            node=self.node, npx=self.npx, python_executable=self.python,
            header_helper=self.header, stdio_helper=self.stdio,
        )

    def test_absent_marker_selects_only_xats_without_copying_the_token(self):
        result = self.resolve()
        self.assertEqual(result.name, "xats")
        self.assertIsInstance(result.codex_server, HttpCommunicationServer)
        self.assertEqual(result.codex_server.url, "http://127.0.0.1:9100/mcp")
        self.assertEqual(result.codex_server.enabled_tools, XATS_COMMUNICATION_TOOLS)
        self.assertEqual(result.claude_tools, XATS_COMMUNICATION_TOOLS)
        self.assertIn(str(self.header), result.codex_server.header_helper)
        self.assertEqual(result.claude_server_name, MCP_SERVER_NAME)
        self.assertEqual(list(result.claude_config["mcpServers"]), [MCP_SERVER_NAME])
        self.assertNotIn("test-only-secret", repr(result))

    def test_xats_registration_probe_reads_only_the_exact_claude_identity(self):
        database = self.xats / "messages.sqlite"
        connection = sqlite3.connect(database)
        connection.execute(
            "CREATE TABLE agents (agent_id TEXT, agent_type TEXT, team TEXT, "
            "name TEXT, runtime_ui_pid INTEGER)")
        connection.execute(
            "INSERT INTO agents VALUES ('agent-1','claude-code','spec-guard-local',?,?)",
            ("review-12345678", 4321),
        )
        connection.commit()
        connection.close()
        database.chmod(0o600)
        probe = self.resolve().claude_registration_probe
        self.assertIsNotNone(probe)
        self.assertTrue(probe("review-12345678", 4321, "session-1", "safe-review"))
        self.assertFalse(probe("review-12345678", 9999, "session-1", "safe-review"))
        self.assertTrue(probe(
            "review-12345678", None, "session-1", "bounded-development"))
        database.chmod(0o644)
        self.assertIsNone(probe(
            "review-12345678", 4321, "session-1", "safe-review"))

    def test_native_marker_selects_only_live_native_mailbox_with_backups_enabled(self):
        self.marker.write_text(json.dumps({
            "backend": "native", "commit": BRIDGE_COMMIT,
        }), encoding="utf-8")
        self.marker.chmod(0o600)
        result = self.resolve()
        self.assertEqual(result.name, "native")
        self.assertIsInstance(result.codex_server, CommunicationServer)
        self.assertEqual(result.codex_server.command, self.node.resolve())
        self.assertEqual(result.codex_server.enabled_tools, COMMUNICATION_TOOLS)
        self.assertEqual(result.claude_tools, COMMUNICATION_TOOLS)
        self.assertNotIn("BRIDGE_BACKUPS", result.codex_server.environment)
        self.assertEqual(result.claude_server_name, CLAUDE_SERVER_NAME)
        self.assertIsNotNone(result.claude_registration_probe)
        serialized = json.dumps(result.claude_config)
        for hidden in ("ask_codex", "review_with_codex", "orchestration"):
            self.assertNotIn(hidden, serialized)
        self.assertNotIn(MCP_SERVER_NAME, serialized)

        database = self.native / "mailbox" / "bridge.sqlite"
        connection = sqlite3.connect(database)
        connection.executescript("""
            CREATE TABLE agents (
                name TEXT PRIMARY KEY, capabilities TEXT, registered_at TEXT,
                last_seen TEXT, retired_at TEXT);
            CREATE TABLE wake_targets (agent TEXT PRIMARY KEY, target TEXT);
            PRAGMA user_version = 2;
        """)
        connection.execute(
            "INSERT INTO agents VALUES (?,?,?,?,NULL)",
            ("review-12345678", "[]", "now", "now"),
        )
        connection.execute(
            "INSERT INTO wake_targets VALUES (?,?)",
            ("review-12345678", json.dumps({
                "app": "claude", "sessionId": "session-exact",
            })),
        )
        connection.commit()
        connection.close()
        database.chmod(0o600)
        probe = result.claude_registration_probe
        self.assertTrue(probe(
            "review-12345678", None, "session-exact", "safe-review"))
        self.assertFalse(probe(
            "review-12345678", None, "session-copy", "safe-review"))
        self.assertTrue(probe(
            "review-12345678", None, "session-copy", "bounded-development"))

    def test_invalid_marker_fails_closed_without_xats_fallback(self):
        self.marker.write_text('{"backend":"xats"}', encoding="utf-8")
        self.marker.chmod(0o600)
        with self.assertRaisesRegex(BackendUnavailable, "backend-invalid"):
            self.resolve()

    def test_native_result_route_requires_one_exact_live_origin_and_reads_only_metadata(self):
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

        connection = sqlite3.connect(database)
        connection.execute(
            "INSERT INTO agents VALUES (?,?,?,?,NULL)",
            ("duplicate-origin", "[]", "now", "now"),
        )
        connection.execute(
            "INSERT INTO wake_targets VALUES (?,?)",
            ("duplicate-origin", json.dumps({
                "app": "codex", "sessionId": "origin-thread-exact",
            })),
        )
        connection.commit()
        connection.close()
        self.assertIsNone(native_result_route(
            database, "codex", "origin-thread-exact", "delegation-12345678"))

    def test_xats_result_route_uses_exact_delivery_identity_and_subject(self):
        database = self.xats / "messages.sqlite"
        connection = sqlite3.connect(database)
        connection.executescript("""
            CREATE TABLE agents (
                agent_id TEXT PRIMARY KEY, agent_type TEXT, device TEXT,
                team TEXT, name TEXT, delivery_kind TEXT,
                delivery_payload TEXT);
            CREATE TABLE messages (
                id TEXT PRIMARY KEY, from_agent_id TEXT, to_agent_id TEXT,
                subject TEXT, body TEXT);
        """)
        connection.execute(
            "INSERT INTO agents VALUES (?,?,?,?,?,?,?)",
            ("origin-id", "claude-code", "local", "spec-guard-local",
             "origin-claude", "claude-channel", json.dumps({
                 "channel_session_id": "origin-session-exact",
             })),
        )
        connection.execute(
            "INSERT INTO agents VALUES (?,?,?,?,?,?,?)",
            ("target-id", "codex", "local", "spec-guard-local",
             "target-codex", "none", None),
        )
        connection.commit()
        connection.close()
        database.chmod(0o600)

        route = xats_result_route(
            database, "claude", "origin-session-exact", "delegation-87654321")
        self.assertEqual(route, MailboxResultRoute(
            "xats", "origin-claude", "spec-guard-result:delegation-87654321"))
        self.assertEqual(route.transport, "spec-guard-bridge")
        self.assertFalse(xats_result_probe(database, route, "target-codex"))

        connection = sqlite3.connect(database)
        connection.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?)",
            ("message-1", "target-id", "origin-id", route.key,
             "private result body"),
        )
        connection.commit()
        connection.close()
        self.assertTrue(xats_result_probe(database, route, "target-codex"))
        self.assertFalse(xats_result_probe(database, route, "wrong-target"))

        connection = sqlite3.connect(database)
        connection.execute(
            "INSERT INTO agents VALUES (?,?,?,?,?,?,?)",
            ("duplicate-id", "claude-code", "local", "spec-guard-local",
             "duplicate-origin", "claude-channel", json.dumps({
                 "channel_session_id": "origin-session-exact",
             })),
        )
        connection.commit()
        connection.close()
        self.assertIsNone(xats_result_route(
            database, "claude", "origin-session-exact", "delegation-87654321"))


if __name__ == "__main__":
    unittest.main()
