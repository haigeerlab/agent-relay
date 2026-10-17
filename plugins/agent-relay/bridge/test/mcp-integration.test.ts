import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

import { BridgeStore } from "../src/bridge-store.js";
import { CLAUDE_EXPIRED_RECEIPT } from "../src/claude-wake.js";
import { retireAgent } from "../src/lifecycle.js";
import { CLAUDE_HOLD_EXPLANATION } from "../src/notices.js";
import { OFFLINE_WAKE_WINDOW_MS, REARMED_DETAIL } from "../src/wake-queue.js";

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));

async function connect(name: string, dbPath: string, extraEnv: Record<string, string> = {}) {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ["--import", "tsx", "src/server.ts"],
    cwd: projectRoot,
    env: {
      PATH: process.env.PATH ?? "",
      HOME: process.env.HOME ?? "",
      BRIDGE_DB_PATH: dbPath,
      BRIDGE_BACKUPS: "0",
      XDG_DATA_HOME: join(dirname(dbPath), "data"),
      ...extraEnv,
    },
    stderr: "pipe",
  });
  const client = new Client({ name, version: "1.0.0" });
  await client.connect(transport);
  return client;
}

type CallResult = Awaited<ReturnType<Client["callTool"]>>;

function payload(result: CallResult) {
  const first = (result.content as Array<{ type: string; text?: string }>)[0];
  assert.equal(first?.type, "text");
  assert.equal(result.isError ?? false, false, first?.text);
  return JSON.parse(first?.text ?? "") as Record<string, unknown>;
}

function errorText(result: CallResult): string {
  assert.equal(result.isError, true);
  return (result.content as Array<{ text?: string }>)[0]?.text ?? "";
}

test("two independent MCP clients exchange and acknowledge a message", async () => {
  const dir = mkdtempSync(join(tmpdir(), "claude-codex-bridge-mcp-"));
  const dbPath = join(dir, "bridge.sqlite");
  const claude = await connect("claude-test-client", dbPath);
  const codex = await connect("codex-test-client", dbPath);

  try {
    // agent-relay legacy-cli-cleanup D96: the server introduces itself by the product's name.
    assert.equal(claude.getServerVersion()?.name, "agent-relay");
    const tools = await claude.listTools();
    assert.deepEqual(
      tools.tools.map((tool) => tool.name).sort(),
      [
        "bridge_ack",
        "bridge_agents",
        "bridge_inbox",
        "bridge_outbox",
        "bridge_register",
        "bridge_send",
        "bridge_sessions",
        "bridge_thread",
        "bridge_wait",
        "bridge_wake_status",
      ].sort(),
    );

    await claude.callTool({ name: "bridge_register", arguments: { agent: "claude", capabilities: ["architecture"] } });
    await codex.callTool({ name: "bridge_register", arguments: { agent: "codex", capabilities: ["implementation"] } });

    const sent = payload(
      await claude.callTool({
        name: "bridge_send",
        arguments: { from: "claude", to: "codex", body: "Please verify the implementation", threadId: "integration-test" },
      }),
    );
    // agent-relay long-messages D150: the send result carries the length, not the body.
    assert.equal("body" in sent, false);
    assert.equal(sent.bodyLength, "Please verify the implementation".length);
    // agent-relay acceptance-030-gaps D72: "codex" registered without wake and without a known host.
    assert.deepEqual(sent.warnings,
      ['"codex" has no wake binding and no known host; it sees this message only when it reads its inbox.']);

    const inbox = payload(await codex.callTool({ name: "bridge_inbox", arguments: { agent: "codex" } }));
    assert.equal(inbox.count, 1);
    assert.equal(inbox.totalUnread, 1);
    const messages = inbox.messages as Array<{ id: number; body: string }>;
    assert.equal(messages[0]?.body, "Please verify the implementation");

    const ack = payload(await codex.callTool({ name: "bridge_ack", arguments: { agent: "codex", ids: [messages[0]?.id] } }));
    assert.equal(ack.acknowledged, 1);
    assert.equal(ack.remainingUnread, 0);

    const waiting = codex.callTool({
      name: "bridge_wait",
      arguments: { agent: "codex", fromAgent: "claude", threadId: "automatic-loop", timeoutSeconds: 2 },
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    await claude.callTool({
      name: "bridge_send",
      arguments: { from: "claude", to: "codex", body: "This should wake the waiting Codex turn", threadId: "automatic-loop" },
    });
    const awakened = payload(await waiting);
    assert.equal(awakened.timedOut, false);
    assert.equal(awakened.count, 1);
    assert.equal((awakened.messages as Array<{ body: string }>)[0]?.body, "This should wake the waiting Codex turn");
  } finally {
    await Promise.all([claude.close(), codex.close()]);
  }
});

test("the bridge guards addressing, pages output and closes out finished agents", async () => {
  const dir = mkdtempSync(join(tmpdir(), "claude-codex-bridge-guards-"));
  const dbPath = join(dir, "bridge.sqlite");
  const client = await connect("guards-client", dbPath);
  try {
    assert.match(errorText(await client.callTool({ name: "bridge_register", arguments: { agent: "bridge" } })), /reserved/);
    assert.match(
      errorText(await client.callTool({ name: "bridge_register", arguments: { agent: "01900000-0000-7000-8000-000000000000" } })),
      /session ID/,
    );
    await client.callTool({ name: "bridge_register", arguments: { agent: "lead" } });
    await client.callTool({ name: "bridge_register", arguments: { agent: "codex-worker" } });

    const typo = errorText(await client.callTool({ name: "bridge_send", arguments: { from: "lead", to: "codex-workr", body: "hi" } }));
    assert.match(typo, /Did you mean: codex-worker/);
    const later = payload(
      await client.callTool({ name: "bridge_send", arguments: { from: "lead", to: "not-yet", body: "hi", allowUnregistered: true } }),
    );
    assert.match(String((later.warnings as string[])[0]), /No agent named/);
    // agent-relay identity-check: an unregistered sender is refused (it was a warning upstream).
    assert.match(errorText(await client.callTool({ name: "bridge_send", arguments: { from: "ghost", to: "lead", body: "hi" } })),
      /"ghost" is not registered/);

    for (const body of ["one", "two", "three"]) {
      await client.callTool({ name: "bridge_send", arguments: { from: "lead", to: "codex-worker", body, threadId: "paging" } });
    }
    const page = payload(await client.callTool({ name: "bridge_inbox", arguments: { agent: "codex-worker", limit: 2 } }));
    assert.equal(page.count, 2);
    assert.equal(page.hasMore, true);
    const thread = payload(await client.callTool({ name: "bridge_thread", arguments: { threadId: "paging", limit: 2 } }));
    assert.deepEqual((thread.messages as Array<{ body: string }>).map((message) => message.body), ["two", "three"]);
    assert.equal(thread.total, 3);

    const outbox = payload(await client.callTool({ name: "bridge_outbox", arguments: { agent: "lead" } }));
    assert.equal(outbox.totalUnacknowledged, 4);

    // agent-relay orchestrator-removal D91: retiring is the CLI's job (`retire`), not an MCP tool.
    const store = new BridgeStore(dbPath);
    try {
      assert.equal(retireAgent(store, "codex-worker", { by: "user", note: "done" }).closed, 3);
    } finally {
      store.close();
    }
    assert.match(
      errorText(await client.callTool({ name: "bridge_send", arguments: { from: "lead", to: "codex-worker", body: "more" } })),
      /retired/,
    );
    const agents = payload(await client.callTool({ name: "bridge_agents", arguments: {} }));
    assert.deepEqual((agents.agents as Array<{ name: string }>).map((agent) => agent.name), ["lead"]);
  } finally {
    await client.close();
  }
});

test("wake: auto binds the conversation that hosts the bridge process", async () => {
  const dir = mkdtempSync(join(tmpdir(), "claude-codex-bridge-auto-"));
  const client = await connect("auto-client", join(dir, "bridge.sqlite"), { CLAUDE_CODE_SESSION_ID: "session-under-test" });
  try {
    const registered = payload(await client.callTool({ name: "bridge_register", arguments: { agent: "auto-agent", wake: "auto" } }));
    assert.deepEqual(registered.wake, { app: "claude", sessionId: "session-under-test" });
    const sessions = payload(await client.callTool({ name: "bridge_sessions", arguments: {} }));
    assert.deepEqual(sessions.thisSession, { app: "claude", sessionId: "session-under-test" });
    const unbound = payload(await client.callTool({ name: "bridge_register", arguments: { agent: "auto-agent", wake: null } }));
    assert.equal(unbound.wake, null);
  } finally {
    await client.close();
  }
});

// agent-relay expiry-notice-reason D215: the list explanation follows Claude's own word, not words in a detail.
test("bridge_wake_status explains a hold only for a real Claude hold", async () => {
  const dir = mkdtempSync(join(tmpdir(), "claude-codex-bridge-mcp-"));
  const dbPath = join(dir, "bridge.sqlite");
  const store = new BridgeStore(dbPath);
  const ping = (to: string) => {
    store.wakes.bind(to, { app: "claude", sessionId: `${to}-session` });
    store.send({ fromAgent: "sender", toAgent: to, body: "hi" });
    return store.wakes.claim(Date.now())!;
  };
  store.wakes.finish(ping("offline-only"), { state: "pending", reason: "offline", detail: "not running" });
  assert.equal(store.wakes.claim(Date.now() + OFFLINE_WAKE_WINDOW_MS + 3_600_000), null);
  store.wakes.finish(ping("rearmed-only"), { state: "accepted", detail: REARMED_DETAIL });
  store.wakes.finish(ping("really-held"), { state: "refused", detail: CLAUDE_EXPIRED_RECEIPT });
  store.close();

  const client = await connect("wake-status-client", dbPath);
  try {
    const status = async (agent: string) =>
      payload(await client.callTool({ name: "bridge_wake_status", arguments: { agent } }));
    const offline = await status("offline-only");
    assert.equal((offline.jobs as Array<{ state: string }>)[0]?.state, "expired");
    assert.equal(offline.explanation, undefined);
    assert.equal((await status("rearmed-only")).explanation, undefined);
    assert.equal((await status("really-held")).explanation, CLAUDE_HOLD_EXPLANATION);
  } finally {
    await client.close();
  }
});

// agent-relay request-closing D217, D219, D222: through the server, the result says what was closed.
test("bridge_send takes alsoAnswers and withdraws and echoes closed", async () => {
  const dir = mkdtempSync(join(tmpdir(), "claude-codex-bridge-mcp-"));
  const dbPath = join(dir, "bridge.sqlite");
  const client = await connect("closing-client", dbPath);
  try {
    for (const agent of ["asker", "twin", "helper"]) {
      await client.callTool({ name: "bridge_register", arguments: { agent } });
    }
    const send = async (args: Record<string, unknown>) => payload(await client.callTool({ name: "bridge_send", arguments: args }));
    const a = await send({ from: "asker", to: "helper", body: "q", expectsReply: true });
    const b = await send({ from: "twin", to: "helper", body: "q too", expectsReply: true });
    const answer = await send({ from: "helper", to: "asker", body: "done", replyTo: a.id, alsoAnswers: [b.id] });
    assert.deepEqual(answer.closed, [{ id: b.id, kind: "answered" }]);
    const plain = await send({ from: "helper", to: "asker", body: "fyi" });
    assert.equal(plain.closed, undefined, "no closed field when neither list is given");
    const c = await send({ from: "asker", to: "helper", body: "another", expectsReply: true });
    const withdrawn = await send({ from: "asker", to: "helper", body: "never mind", withdraws: [c.id] });
    assert.deepEqual(withdrawn.closed, [{ id: c.id, kind: "withdrawn" }]);
    const refused = await client.callTool({ name: "bridge_send", arguments: { from: "helper", to: "asker", body: "x",
      alsoAnswers: [b.id] } });
    assert.match(errorText(refused), new RegExp(`#${b.id}.*already answered`));
  } finally {
    await client.close();
  }
});
