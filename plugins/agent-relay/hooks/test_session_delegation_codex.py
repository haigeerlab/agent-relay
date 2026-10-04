"""Codex app-server adapter tests with fake binaries and protocol clients."""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest

from session_delegation import AuthorizationRequest, DelegationStore
from session_delegation_codex import (
    COMMUNICATION_TOOLS,
    CodexAdapter,
    CodexAdapterError,
    CodexInstallation,
    CommunicationServer,
    HttpCommunicationServer,
    JsonRpcClient,
    RpcRejected,
    RpcReply,
    RpcUncertain,
    TurnOutcome,
    XATS_COMMUNICATION_TOOLS,
    _bound_prompt,
    build_process_command,
    discover_app_managed_codex,
    parse_mcp_inventory,
    read_mcp_inventory,
    sanitized_environment,
)


NOW = 1_800_000_000


class FakeTransport:
    def __init__(self, messages):
        self.messages = deque(messages)
        self.sent = []
        self.closed = False

    def send(self, message):
        self.sent.append(message)

    def receive(self, timeout):
        if not self.messages:
            raise TimeoutError("fake timeout")
        item = self.messages.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


class ScriptedClient:
    def __init__(self, replies, outcome=None):
        self.replies = deque(replies)
        self.outcome = outcome
        self.calls = []
        self.initialized = False
        self.closed = False

    def initialize(self):
        self.initialized = True

    def request(self, method, params, timeout=60):
        self.calls.append((method, params))
        expected, value = self.replies.popleft()
        if method != expected:
            raise AssertionError("expected %s, got %s" % (expected, method))
        if isinstance(value, Exception):
            raise value
        return RpcReply(value, ())

    def wait_turn(self, turn_id, prior=(), require_registration=False, timeout=300):
        self.calls.append(("wait_turn", {
            "turnId": turn_id,
            "requireRegistration": require_registration,
        }))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def close(self):
        self.closed = True


class InstallationAndIsolationTests(unittest.TestCase):
    def test_host_prompt_allows_control_envelope_after_maximum_user_body(self):
        prompt = _bound_prompt(
            "x" * 20_800, "thread-12345678", "review", "bridge_register")
        self.assertIn("<spec-guard-control>", prompt)
        with self.assertRaisesRegex(CodexAdapterError, "delegation-prompt-invalid"):
            _bound_prompt(
                "x" * 24_001, "thread-12345678", "review", "bridge_register")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sg-codex-adapter-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def installation(self, version="0.160.0"):
        package = self.root / "packages" / "app-server-daemon"
        release = package / "releases" / (version + "-aarch64-apple-darwin")
        binary = release / "bin" / "codex"
        binary.parent.mkdir(parents=True)
        binary.write_text("fake", encoding="utf-8")
        binary.chmod(0o700)
        (package / "current").symlink_to(release, target_is_directory=True)
        return package, binary

    def test_discovers_only_app_managed_current_and_rejects_older_release(self):
        package, binary = self.installation()
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            return CompletedProcess(command, 0, "codex-cli 0.160.0\n", "")

        found = discover_app_managed_codex(package, run=run)
        self.assertEqual(found.binary, binary.resolve())
        self.assertEqual(found.version, "0.160.0")
        self.assertEqual(calls[0][0], [str(binary.resolve()), "--version"])
        self.assertNotIn("codex", calls[0][0][0].split("/")[-2:-1])

        old_package = self.root / "old" / "app-server-daemon"
        old_release = old_package / "releases" / "0.154.0-aarch64-apple-darwin"
        old_binary = old_release / "bin" / "codex"
        old_binary.parent.mkdir(parents=True)
        old_binary.write_text("fake", encoding="utf-8")
        old_binary.chmod(0o700)
        (old_package / "current").symlink_to(old_release, target_is_directory=True)
        with self.assertRaisesRegex(CodexAdapterError, "unsupported-version"):
            discover_app_managed_codex(
                old_package,
                run=lambda command, **kwargs: CompletedProcess(
                    command, 0, "codex-cli 0.154.0\n", ""
                ),
            )

    def test_inventory_keeps_only_non_secret_disabled_transport_identity(self):
        raw = json.dumps([
            {
                "name": "stdio_server",
                "transport": {
                    "type": "stdio", "command": "npx", "args": ["pkg"],
                    "cwd": "/tmp", "env": {"TOKEN": "secret"},
                },
            },
            {
                "name": "relative_cwd_server",
                "transport": {
                    "type": "stdio", "command": "node", "args": ["server.js"],
                    "cwd": ".", "env": {"TOKEN": "secret"},
                },
            },
            {
                "name": "http_server",
                "transport": {
                    "type": "streamable_http", "url": "https://mcp.example.test/api",
                    "headers": {"Authorization": "secret"},
                },
            },
        ])
        inventory = parse_mcp_inventory(raw)
        self.assertEqual(inventory["stdio_server"], {
            "enabled": False, "command": "npx", "args": ["pkg"], "cwd": "/tmp",
        })
        self.assertEqual(inventory["http_server"], {
            "enabled": False, "url": "https://mcp.example.test/api",
        })
        self.assertEqual(inventory["relative_cwd_server"], {
            "enabled": False, "command": "node", "args": ["server.js"],
        })
        self.assertNotIn("secret", json.dumps(inventory))
        with self.assertRaisesRegex(CodexAdapterError, "secret-bearing-url"):
            parse_mcp_inventory(json.dumps([{
                "name": "bad",
                "transport": {
                    "type": "http", "url": "https://user:pass@example.test/mcp?token=x",
                },
            }]))

    def test_inventory_uses_the_same_app_managed_binary_and_sanitized_environment(self):
        project = self.root / "project"
        project.mkdir()
        binary = self.root / "managed-codex"
        binary.write_text("fake", encoding="utf-8")
        installation = CodexInstallation(binary, "0.160.0", self.root)
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            return CompletedProcess(command, 0, "[]\n", "")

        inventory = read_mcp_inventory(
            installation,
            project,
            run=run,
        )
        self.assertEqual(inventory, {})
        self.assertEqual(calls[0][0], [str(binary), "mcp", "list", "--json"])
        self.assertEqual(calls[0][1]["cwd"], str(project.resolve()))
        for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
            self.assertNotIn(name, calls[0][1]["env"])

    def test_process_command_disables_inherited_surfaces_and_omits_model(self):
        binary = self.root / "codex"
        binary.write_text("fake", encoding="utf-8")
        binary.chmod(0o700)
        node = self.root / "node"
        node.write_text("fake", encoding="utf-8")
        node.chmod(0o700)
        server = self.root / "server.js"
        server.write_text("fake", encoding="utf-8")
        communication = CommunicationServer(
            command=node,
            args=(str(server),),
            environment={
                "BRIDGE_DB_PATH": str(self.root / "bridge.sqlite"),
                "XDG_DATA_HOME": str(self.root / "data"),
                "BRIDGE_BACKUPS": "0",
            },
        )
        command = build_process_command(
            CodexInstallation(binary.resolve(), "0.160.0", self.root),
            {"inherited": {"enabled": False, "command": "npx", "args": ["pkg"]}},
            communication,
        )
        joined = " ".join(command)
        for feature in (
            "apps", "plugins", "browser_use", "browser_use_external",
            "computer_use", "multi_agent",
        ):
            self.assertIn("--disable " + feature, joined)
        self.assertIn("enabled_tools", joined)
        for tool in COMMUNICATION_TOOLS:
            self.assertIn(tool, joined)
        for forbidden in ("model=", "worker", "orchestration", "review/start"):
            self.assertNotIn(forbidden, joined)

    def test_xats_http_server_uses_only_loopback_and_a_nonsecret_header_helper(self):
        binary = self.root / "codex"
        binary.write_text("fake", encoding="utf-8")
        binary.chmod(0o700)
        helper = self.root / "header-helper.py"
        helper.write_text("fake", encoding="utf-8")
        command = build_process_command(
            CodexInstallation(binary.resolve(), "0.160.0", self.root),
            {},
            HttpCommunicationServer(
                "http://127.0.0.1:9100/mcp",
                "/usr/bin/python3 %s --config-dir /private/runtime" % helper,
                XATS_COMMUNICATION_TOOLS,
            ),
        )
        joined = " ".join(command)
        self.assertIn("http://127.0.0.1:9100/mcp", joined)
        self.assertIn("http_headers_helper", joined)
        self.assertIn(str(helper), joined)
        self.assertNotIn("Bearer", joined)
        self.assertNotIn("token=", joined.lower())
        for tool in XATS_COMMUNICATION_TOOLS:
            self.assertIn(tool, joined)
        self.assertNotIn("bridge_register", joined)

        with self.assertRaisesRegex(CodexAdapterError, "loopback"):
            build_process_command(
                CodexInstallation(binary.resolve(), "0.160.0", self.root),
                {},
                HttpCommunicationServer(
                    "https://example.test/mcp", "/usr/bin/python3 helper.py",
                ),
            )
        with self.assertRaisesRegex(CodexAdapterError, "communication-tools-invalid"):
            build_process_command(
                CodexInstallation(binary.resolve(), "0.160.0", self.root),
                {},
                HttpCommunicationServer(
                    "http://127.0.0.1:9100/mcp",
                    "/usr/bin/python3 helper.py", ("ask_codex",),
                ),
            )

    def test_environment_strips_both_hosts_ambient_session_identity(self):
        environment = sanitized_environment({
            "PATH": "/bin", "CODEX_THREAD_ID": "origin",
            "CODEX_SESSION_ID": "origin-session", "CLAUDE_CODE_SESSION_ID": "claude",
        })
        self.assertEqual(environment, {"PATH": "/bin"})


class JsonRpcTests(unittest.TestCase):
    def test_handshake_and_out_of_order_turn_events_require_registration(self):
        transport = FakeTransport([
            {"id": 1, "result": {"userAgent": "codex"}},
            {"method": "turn/completed", "params": {
                "turn": {"id": "turn-1", "status": "completed"},
            }},
            {"method": "item/completed", "params": {"item": {
                "type": "mcpToolCall", "server": "spec_guard_delegation",
                "tool": "bridge_register", "status": "completed",
            }}},
        ])
        client = JsonRpcClient(transport, timeout=0.1)
        client.initialize()
        outcome = client.wait_turn("turn-1", require_registration=True, timeout=0.1)
        self.assertEqual(outcome.status, "completed")
        self.assertTrue(outcome.registered)
        self.assertEqual(transport.sent[0]["method"], "initialize")
        self.assertEqual(transport.sent[1]["method"], "initialized")

    def test_response_loss_preserves_notifications_as_uncertain_evidence(self):
        transport = FakeTransport([
            {"id": 1, "result": {}},
            {"method": "thread/started", "params": {"thread": {"id": "thread-seen"}}},
            TimeoutError("lost response"),
        ])
        client = JsonRpcClient(transport, timeout=0.1)
        client.initialize()
        with self.assertRaises(RpcUncertain) as caught:
            client.request("thread/start", {"cwd": "/tmp"}, timeout=0.1)
        self.assertEqual(caught.exception.observed_thread_ref, "thread-seen")

    def test_xats_registration_event_uses_its_real_tool_name(self):
        transport = FakeTransport([
            {"id": 1, "result": {}},
            {"method": "item/completed", "params": {"item": {
                "type": "mcpToolCall", "server": "spec_guard_delegation",
                "tool": "register_agent", "status": "completed",
            }}},
            {"method": "turn/completed", "params": {
                "turn": {"id": "turn-xats", "status": "completed"},
            }},
        ])
        client = JsonRpcClient(
            transport, timeout=0.1, registration_tool="register_agent")
        client.initialize()
        self.assertTrue(client.wait_turn(
            "turn-xats", require_registration=True, timeout=0.1).registered)

    def test_protocol_error_exposes_only_the_numeric_code(self):
        transport = FakeTransport([
            {"id": 1, "result": {}},
            {"id": 2, "error": {
                "code": -32601,
                "message": "secret host detail",
                "data": {"token": "must-not-leak"},
            }},
        ])
        client = JsonRpcClient(transport, timeout=0.1)
        client.initialize()
        with self.assertRaisesRegex(RpcRejected, "-32601") as caught:
            client.request("thread/read", {"threadId": "thread-1"})
        self.assertEqual(caught.exception.method, "thread/read")
        self.assertEqual(caught.exception.code, -32601)
        self.assertNotIn("secret host detail", str(caught.exception))
        self.assertNotIn("must-not-leak", str(caught.exception))

    def test_protocol_error_replaces_a_non_numeric_code(self):
        transport = FakeTransport([
            {"id": 1, "result": {}},
            {"id": 2, "error": {
                "code": {"token": "must-not-leak"},
                "message": "secret host detail",
            }},
        ])
        client = JsonRpcClient(transport, timeout=0.1)
        client.initialize()

        with self.assertRaisesRegex(RpcRejected, "unknown") as caught:
            client.request("thread/read", {"threadId": "thread-1"})

        self.assertEqual(caught.exception.code, "unknown")
        self.assertNotIn("secret host detail", str(caught.exception))
        self.assertNotIn("must-not-leak", str(caught.exception))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sg-codex-flow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.store = DelegationStore(self.root / "state", now=lambda: NOW)
        request = AuthorizationRequest(
            authority="direct-user", horizon="task", origin_host="claude",
            origin_session="origin-session", project_root=self.project,
            repo_identity="git:example/project", baseline="a" * 40, dirty=False,
            target_hosts=("codex",), permission_intent="safe-review",
            host_permission=None, max_sessions=1, expires_at=NOW + 600, depth=0,
            idempotency_key="codex-request-123", summary="Review current diff",
        )
        self.envelope = self.store.authorize(request)
        self.claim = self.store.claim_launch(
            self.envelope.envelope_id, "codex-launch-123", "codex",
            self.project, "a" * 40, "safe-review",
        )
        binary = self.root / "codex"
        binary.write_text("fake", encoding="utf-8")
        binary.chmod(0o700)
        self.installation = CodexInstallation(binary.resolve(), "0.160.0", self.root)

    def thread_result(self, sandbox=None, thread_id="thread-1"):
        return {
            "thread": {"id": thread_id, "sessionId": thread_id},
            "cwd": str(self.project.resolve()),
            "approvalPolicy": "never",
            "sandbox": sandbox or {"type": "readOnly", "networkAccess": False},
            "model": "configured-default",
            "modelProvider": "openai",
        }

    def catalog(self):
        return {"data": [
            {"name": "disabled", "tools": {}},
            {"name": "spec_guard_delegation",
             "tools": {tool: {} for tool in COMMUNICATION_TOOLS}},
        ]}

    def adapter(self, clients):
        pending = deque(clients)
        return CodexAdapter(
            self.store, self.installation, (str(self.installation.binary), "app-server"),
            {"PATH": "/bin"}, lambda: pending.popleft(),
        )

    def successful_client(self, thread_id="thread-1", turn_id="turn-1"):
        return ScriptedClient([
            ("thread/start", self.thread_result(thread_id=thread_id)),
            ("mcpServerStatus/list", self.catalog()),
            ("turn/start", {"turn": {"id": turn_id, "status": "inProgress"}}),
        ], TurnOutcome("completed", True, "done"))

    def test_create_binds_exact_thread_uses_effective_narrow_permission_and_omits_model(self):
        client = self.successful_client()
        result = self.adapter([client]).create(
            self.claim.delegation_id, "Review this diff\nand report findings"
        )
        self.assertEqual(result.state, "completed")
        self.assertEqual(result.thread_ref, "thread-1")
        stored = self.store.get_delegation(self.claim.delegation_id)
        self.assertEqual(stored.state, "completed")
        self.assertEqual(stored.host_ref, "thread-1")
        self.assertEqual(stored.last_turn_ref, "turn-1")
        for method, params in client.calls:
            if method in ("thread/start", "turn/start"):
                self.assertNotIn("model", params)
        start = client.calls[0][1]
        self.assertEqual(start["sandbox"], "read-only")
        self.assertEqual(start["approvalPolicy"], "never")
        turn = next(params for method, params in client.calls if method == "turn/start")
        self.assertIn("thread-1", turn["input"][0]["text"])
        self.assertIn("Review this diff\nand report findings", turn["input"][0]["text"])

    def test_broader_effective_permission_fails_closed_before_turn(self):
        client = ScriptedClient([
            ("thread/start", self.thread_result({"type": "dangerFullAccess"})),
        ])
        with self.assertRaisesRegex(CodexAdapterError, "effective-permission-expanded"):
            self.adapter([client]).create(self.claim.delegation_id, "Review")
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state, "unknown")
        self.assertNotIn("turn/start", [method for method, _ in client.calls])

    def test_inherited_or_hidden_tool_catalog_fails_before_turn(self):
        unsafe_catalog = self.catalog()
        unsafe_catalog["data"][0]["tools"] = {"hidden_worker": {}}
        client = ScriptedClient([
            ("thread/start", self.thread_result()),
            ("mcpServerStatus/list", unsafe_catalog),
        ])
        with self.assertRaisesRegex(CodexAdapterError, "inherited-tool-catalog-not-empty"):
            self.adapter([client]).create(self.claim.delegation_id, "Review")
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state, "unknown")

    def test_bounded_development_requires_a_clean_isolated_worktree(self):
        request = AuthorizationRequest(
            authority="direct-user", horizon="task", origin_host="claude",
            origin_session="origin-session", project_root=self.project,
            repo_identity="git:example/project", baseline="a" * 40, dirty=False,
            target_hosts=("codex",), permission_intent="bounded-development",
            host_permission=None, max_sessions=1, expires_at=NOW + 600, depth=0,
            idempotency_key="codex-development-123", summary="Implement bounded change",
        )
        envelope = self.store.authorize(request)
        claim = self.store.claim_launch(
            envelope.envelope_id, "codex-development-launch", "codex",
            self.project, "a" * 40, "bounded-development",
        )
        with self.assertRaisesRegex(CodexAdapterError, "isolated-clean-worktree-required"):
            self.adapter([]).create(claim.delegation_id, "Implement")

        development = ScriptedClient([
            ("thread/start", self.thread_result({
                "type": "workspaceWrite", "networkAccess": False,
                "writableRoots": [str(self.project.resolve())],
            }, thread_id="thread-development")),
            ("mcpServerStatus/list", self.catalog()),
            ("turn/start", {"turn": {"id": "turn-development",
                                      "status": "inProgress"}}),
        ], TurnOutcome("completed", True, "implemented"))
        result = self.adapter([development]).create(
            claim.delegation_id, "Implement", isolated_worktree=True,
        )
        self.assertEqual(result.state, "completed")
        self.assertEqual(
            self.store.get_delegation(claim.delegation_id).actual_permission,
            "workspaceWrite/never",
        )

    def test_response_loss_retry_does_not_create_a_second_thread(self):
        first = ScriptedClient([
            ("thread/start", RpcUncertain("thread/start", (), "thread-seen")),
        ])
        factory_calls = []

        def factory():
            factory_calls.append(True)
            return first

        adapter = CodexAdapter(
            self.store, self.installation, (str(self.installation.binary), "app-server"),
            {"PATH": "/bin"}, factory,
        )
        initial = adapter.create(self.claim.delegation_id, "Review")
        retry = adapter.create(self.claim.delegation_id, "Review")
        self.assertEqual(initial.state, "unknown")
        self.assertEqual(retry.state, "unknown")
        self.assertEqual(len(factory_calls), 1)
        stored = self.store.get_delegation(self.claim.delegation_id)
        self.assertEqual(stored.host_ref, "thread-seen")

    def test_continue_resumes_exact_thread_and_status_reads_without_guessing(self):
        created = self.successful_client()
        self.adapter([created]).create(self.claim.delegation_id, "Review")
        resumed = ScriptedClient([
            ("thread/resume", self.thread_result()),
            ("mcpServerStatus/list", self.catalog()),
            ("turn/start", {"turn": {"id": "turn-2", "status": "inProgress"}}),
        ], TurnOutcome("completed", False, "follow-up done"))
        status = ScriptedClient([
            ("thread/read", {"thread": {"id": "thread-1", "status": {"type": "idle"}}}),
        ])
        adapter = self.adapter([resumed, status])
        continued = adapter.continue_turn(self.claim.delegation_id, "Check one more thing")
        current = adapter.status(self.claim.delegation_id)
        self.assertEqual(continued.state, "completed")
        self.assertEqual(current.host_status, "idle")
        self.assertEqual(resumed.calls[0][1]["threadId"], "thread-1")
        for method, params in resumed.calls:
            if method in ("thread/resume", "turn/start"):
                self.assertNotIn("model", params)
        self.assertEqual(status.calls[0], (
            "thread/read", {"threadId": "thread-1", "includeTurns": False},
        ))

    def test_uncertain_follow_up_turn_is_not_retried_automatically(self):
        self.adapter([self.successful_client()]).create(self.claim.delegation_id, "Review")
        resumed = ScriptedClient([
            ("thread/resume", self.thread_result()),
            ("mcpServerStatus/list", self.catalog()),
            ("turn/start", RpcUncertain("turn/start", (), None)),
        ])
        adapter = self.adapter([resumed])
        first = adapter.continue_turn(self.claim.delegation_id, "Follow up")
        self.assertEqual(first.state, "unknown")
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state, "unknown")
        with self.assertRaisesRegex(CodexAdapterError, "not-ready-for-follow-up"):
            adapter.continue_turn(self.claim.delegation_id, "Do not duplicate")

    def test_follow_up_rejected_by_host_is_held_without_changing_the_claim(self):
        self.adapter([self.successful_client()]).create(self.claim.delegation_id, "Review")
        resumed = ScriptedClient([
            ("thread/resume", RpcRejected("thread/resume", -32600)),
        ])

        result = self.adapter([resumed]).continue_turn(
            self.claim.delegation_id, "Follow up")

        self.assertEqual(result.state, "held")
        self.assertEqual(result.host_status, "unknown")
        self.assertEqual(result.prerequisite, "host-request-rejected")
        self.assertEqual(
            self.store.get_delegation(self.claim.delegation_id).state,
            "completed",
        )

    def test_malformed_follow_up_turn_response_is_not_retried_automatically(self):
        self.adapter([self.successful_client()]).create(self.claim.delegation_id, "Review")
        resumed = ScriptedClient([
            ("thread/resume", self.thread_result()),
            ("mcpServerStatus/list", self.catalog()),
            ("turn/start", {"turn": {"status": "inProgress"}}),
        ])
        adapter = self.adapter([resumed])
        with self.assertRaisesRegex(CodexAdapterError, "turn-response-invalid"):
            adapter.continue_turn(self.claim.delegation_id, "Follow up")
        self.assertEqual(
            self.store.get_delegation(self.claim.delegation_id).state,
            "unknown",
        )
        with self.assertRaisesRegex(CodexAdapterError, "not-ready-for-follow-up"):
            adapter.continue_turn(self.claim.delegation_id, "Do not duplicate")

    def test_cancel_completed_thread_archives_exact_ref_and_freezes_authorization(self):
        self.adapter([self.successful_client()]).create(self.claim.delegation_id, "Review")
        cancel_client = ScriptedClient([
            ("thread/archive", {}),
        ])
        cancelled = self.adapter([cancel_client]).cancel(self.claim.delegation_id)
        self.assertEqual(cancelled.state, "cancelled")
        self.assertEqual(cancel_client.calls[0], (
            "thread/archive", {"threadId": "thread-1"},
        ))
        self.assertEqual(self.store.get_delegation(self.claim.delegation_id).state, "cancelled")
        self.assertEqual(self.store.get_authorization(self.envelope.envelope_id).state, "cancelled")

    def test_cancel_running_turn_waits_for_interrupted_then_archives(self):
        self.adapter([self.successful_client()]).create(self.claim.delegation_id, "Review")
        self.store.begin_follow_up(self.claim.delegation_id, "turn-active")
        cancel_client = ScriptedClient([
            ("turn/interrupt", {}),
            ("thread/archive", {}),
        ], TurnOutcome("interrupted", False, ""))
        result = self.adapter([cancel_client]).cancel(self.claim.delegation_id)
        self.assertEqual(result.state, "cancelled")
        self.assertEqual([method for method, _ in cancel_client.calls], [
            "turn/interrupt", "wait_turn", "thread/archive",
        ])

    def test_cancel_rejected_by_host_freezes_authority_and_reports_unknown(self):
        self.adapter([self.successful_client()]).create(self.claim.delegation_id, "Review")
        cancel_client = ScriptedClient([
            ("thread/archive", RpcRejected("thread/archive", -32600)),
        ])

        result = self.adapter([cancel_client]).cancel(self.claim.delegation_id)

        self.assertEqual(result.state, "unknown")
        self.assertEqual(result.host_status, "unknown")
        self.assertEqual(result.prerequisite, "host-request-rejected")
        self.assertEqual(
            self.store.get_delegation(self.claim.delegation_id).state,
            "unknown",
        )
        self.assertEqual(
            self.store.get_authorization(self.envelope.envelope_id).state,
            "cancelled",
        )


if __name__ == "__main__":
    unittest.main()
