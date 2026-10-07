"""A delegated session's reworded result retry leaves one result and delivery stays enqueued (idempotency, 2b)."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from session_delegation_backend import MailboxResultRoute, native_result_probe
from session_delegation_control import SessionDelegationController

BRIDGE = Path(__file__).resolve().parent.parent / "bridge"
SEND = """
const { BridgeStore } = await import("./src/bridge-store.ts");
const [path, from, to, threadId, idempotencyKey, body] = process.argv.slice(1);
const store = new BridgeStore(path);
try {
  for (const name of [from, to]) store.register(name);
  console.log(JSON.stringify(store.deliver({ fromAgent: from, toAgent: to, threadId, idempotencyKey, body })));
} catch (error) {
  console.error(error.message);
  process.exitCode = 3;
} finally {
  store.close();
}
"""


class RewordedResultRetryTests(unittest.TestCase):
    def test_the_route_instruction_says_a_key_refusal_means_the_result_is_delivered(self):
        route = SimpleNamespace(backend="native", recipient="origin-agent",
                                key="agent-relay-result:route-1234")
        prompt = SessionDelegationController._with_result_route("Review", route, "turn-1")
        self.assertRegex(prompt, r"already used.*result is already delivered.*do not retry.*report a failure")

    @unittest.skipUnless((BRIDGE / "node_modules").is_dir() and shutil.which("node"), "bridge dependencies not installed")
    def test_a_reworded_retry_is_refused_and_one_result_stays_enqueued(self):
        with tempfile.TemporaryDirectory(prefix="ar-result-retry-") as tmp:
            database = Path(tmp) / "bridge.sqlite"
            base = SimpleNamespace(backend="native", recipient="origin-agent",
                                   key="agent-relay-result:route-1234")
            route = SessionDelegationController._turn_route(base, "Review", "turn-1")
            prompt = SessionDelegationController._with_result_route("Review", route, "turn-1")
            thread = json.loads(re.search(r"threadId (\"[^\"]+\")", prompt).group(1))
            key = json.loads(re.search(r"idempotencyKey (\"[^\"]+\")", prompt).group(1))
            claim = SimpleNamespace(state="completed", target_host="claude", friendly_name="复审",
                                    delegation_id="12345678-1234-1234-1234-123456789abc", host_ref=None)
            sender = SessionDelegationController._target_agent_name(claim)

            def send(body):
                return subprocess.run(
                    ["node", "--import", "tsx", "--input-type=module", "-e", SEND,
                     str(database), sender, "origin-agent", thread, key, body],
                    cwd=BRIDGE, capture_output=True, text=True, timeout=60, check=False)

            self.assertEqual(thread, route.key)
            first = send("审查完成：无阻断问题")
            self.assertEqual(first.returncode, 0, first.stderr)
            retry = send("审查已完成，没有阻断问题")
            self.assertEqual(retry.returncode, 3, retry.stdout)
            self.assertIn("no resend is needed", retry.stderr)
            with sqlite3.connect(database) as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM messages WHERE from_agent=? AND thread_id=?",
                    (sender, thread)).fetchone()[0]
            self.assertEqual(count, 1)
            controller = SessionDelegationController(
                None, lambda _host, _project: None,
                result_route_resolver=lambda _envelope, _claim: base,
                result_probe=lambda observed, who: native_result_probe(
                    database, MailboxResultRoute(observed.backend, observed.recipient, observed.key), who),
            )
            self.assertEqual(controller._delivery(route, claim), "enqueued")


if __name__ == "__main__":
    unittest.main()
