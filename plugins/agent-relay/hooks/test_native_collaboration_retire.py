"""Operator retire keeps unread mail and never touches a real mailbox."""
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from native_collaboration_retire import RetireError, identity_state, main, retire_identity
from native_collaboration_runtime import BRIDGE_COMMIT


# 代替 node：记录参数与环境，并按真实 CLI 的方式把该身份标记为 retired。
FAKE_NODE = """#!%s
import json, os, sqlite3, sys
log = os.path.join(os.path.dirname(os.environ["BRIDGE_DB_PATH"]), "calls.jsonl")
with open(log, "a") as handle:
    handle.write(json.dumps({"argv": sys.argv[1:], "db": os.environ["BRIDGE_DB_PATH"],
                             "data": os.environ["XDG_DATA_HOME"]}) + "\\n")
if sys.argv[2] != "retire" or "--keep-backlog" not in sys.argv:
    sys.exit(7)
with sqlite3.connect(os.environ["BRIDGE_DB_PATH"]) as connection:
    connection.execute("UPDATE agents SET retired_at='now' WHERE name=?", (sys.argv[3],))
""" % sys.executable


class NativeRetireTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sg-native-retire-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "native"
        self.root.mkdir(mode=0o700)
        for name in ("mailbox", "mailbox/backups", "data"):
            (self.root / name).mkdir(mode=0o700)
        (self.root / "dist").mkdir()
        (self.root / "dist" / "server.js").write_text("server\n")
        (self.root / "manifest.json").write_text(json.dumps({"commit": BRIDGE_COMMIT}))
        self.database = self.root / "mailbox" / "bridge.sqlite"
        with sqlite3.connect(self.database) as connection:
            connection.executescript("""
                PRAGMA user_version=2;
                CREATE TABLE agents (name TEXT PRIMARY KEY, registered_at TEXT, retired_at TEXT);
                CREATE TABLE messages (id INTEGER PRIMARY KEY, from_agent TEXT, to_agent TEXT,
                                       created_at TEXT, body TEXT);
                CREATE TABLE acknowledgements (message_id INTEGER, agent TEXT, acked_at TEXT,
                                               PRIMARY KEY (message_id, agent));
                INSERT INTO agents VALUES ('done', '2026-01-02', NULL);
                INSERT INTO agents VALUES ('busy', '2026-01-02', NULL);
                INSERT INTO agents VALUES ('late', '2026-01-05', NULL);
                INSERT INTO agents VALUES ('old', '2026-01-01', '2026-01-03');
                INSERT INTO messages VALUES (1, 'busy', 'done', '2026-01-03', 'handled');
                INSERT INTO acknowledgements VALUES (1, 'done', '2026-01-04');
                INSERT INTO messages VALUES (2, 'done', 'busy', '2026-01-03', 'unread direct');
                INSERT INTO messages VALUES (3, 'busy', '*', '2026-01-04', 'broadcast');
                INSERT INTO acknowledgements VALUES (3, 'done', '2026-01-04');
            """)
        self.database.chmod(0o600)
        self.node = Path(self.tmp.name) / "node"
        self.node.write_text(FAKE_NODE)
        self.node.chmod(0o755)

    def calls(self):
        log = self.root / "mailbox" / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def test_identity_state_counts_direct_and_broadcast_deliveries(self):
        self.assertEqual(identity_state(self.database, "done"), {"state": "active", "unacknowledged": 0})
        self.assertEqual(identity_state(self.database, "busy")["unacknowledged"], 1)
        # 'late' 注册于广播之后，不应被计入；已退役和不存在的身份分别报告。
        self.assertEqual(identity_state(self.database, "late")["unacknowledged"], 0)
        self.assertEqual(identity_state(self.database, "old")["state"], "retired")
        self.assertEqual(identity_state(self.database, "nobody"), {"state": "absent"})

    def test_retires_a_clear_identity_with_the_backlog_kept(self):
        self.assertEqual(retire_identity(self.root, str(self.node), "done", note="session ended"),
                         {"state": "retired", "name": "done"})
        call = self.calls()[0]
        self.assertEqual(call["argv"][1:], ["retire", "done", "--keep-backlog", "--note",
                                             "session ended"])
        self.assertEqual((call["db"], call["data"]), (str(self.database), str(self.root / "data")))
        self.assertEqual(identity_state(self.database, "done")["state"], "retired")

    def test_refuses_an_identity_with_unread_mail_without_calling_the_cli(self):
        for name, pattern in (("busy", "1 unacknowledged"), ("nobody", "no native identity")):
            with self.subTest(name=name):
                with self.assertRaisesRegex(RetireError, pattern):
                    retire_identity(self.root, str(self.node), name)
        self.assertEqual(self.calls(), [])
        self.assertEqual(identity_state(self.database, "busy")["state"], "active")

    def test_already_retired_identity_is_reported_without_a_second_call(self):
        self.assertEqual(retire_identity(self.root, str(self.node), "old"),
                         {"state": "already-retired", "name": "old"})
        self.assertEqual(self.calls(), [])

    def test_cli_success_is_verified_against_the_mailbox(self):
        self.node.write_text("#!/bin/sh\nexit 0\n")
        with self.assertRaisesRegex(RetireError, "did not retire"):
            retire_identity(self.root, str(self.node), "done")

    def test_command_requires_explicit_confirmation(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            main(["--name", "done", "--root", str(self.root), "--node", str(self.node)])
        self.assertEqual(self.calls(), [])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--name", "busy", "--root", str(self.root),
                                   "--node", str(self.node), "--confirm-retire"]), 1)
        self.assertEqual(json.loads(output.getvalue())["state"], "refused")


if __name__ == "__main__":
    unittest.main()
