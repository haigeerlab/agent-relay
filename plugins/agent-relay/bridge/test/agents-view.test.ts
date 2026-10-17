// agent-relay agents-view-polish (D223–D226): bridge_agents pages, message status is open, presence activity, 2 s cap.
import assert from "node:assert/strict";
import { chmodSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { createServer, type Server } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

import { BridgeStore } from "../src/bridge-store.js";
import { retireAgent } from "../src/lifecycle.js";

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));

async function connect(dbPath: string, extraEnv: Record<string, string> = {}) {
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
  const client = new Client({ name: "agents-view", version: "1.0.0" });
  await client.connect(transport);
  return client;
}

type CallResult = Awaited<ReturnType<Client["callTool"]>>;
function payload(result: CallResult) {
  const first = (result.content as Array<{ type: string; text?: string }>)[0];
  assert.equal(result.isError ?? false, false, first?.text);
  return JSON.parse(first?.text ?? "") as Record<string, any>;
}
function errorText(result: CallResult): string {
  assert.equal(result.isError, true);
  return (result.content as Array<{ text?: string }>)[0]?.text ?? "";
}

function mailboxWithRetired(retired: number): string {
  const dir = mkdtempSync(join(tmpdir(), "bridge-agents-view-"));
  const dbPath = join(dir, "bridge.sqlite");
  const store = new BridgeStore(dbPath);
  for (const name of ["alpha", "beta"]) store.register(name, ["review", "architecture"]);
  for (let index = 0; index < retired; index += 1) {
    const name = `old-${String(index).padStart(2, "0")}`;
    store.register(name, Array.from({ length: 20 }, (_, i) => `capability-${i}-${"x".repeat(20)}`));
    retireAgent(store, name, { by: "test", note: "finished ".repeat(40) });
  }
  store.close();
  return dbPath;
}

test("bridge_agents pages with includeRetired and keeps retired entries compact (D223)", async () => {
  const dbPath = mailboxWithRetired(30);
  const client = await connect(dbPath);
  try {
    const seen: string[] = [];
    let afterName: string | undefined;
    let pages = 0;
    for (;;) {
      const page = payload(await client.callTool({ name: "bridge_agents",
        arguments: { includeRetired: true, maxChars: 2000, ...(afterName ? { afterName } : {}) } }));
      pages += 1;
      assert.equal(page.count, page.agents.length);
      assert.ok(page.agents.length >= 1);
      for (const agent of page.agents) {
        seen.push(agent.name);
        if (agent.retiredAt) {
          assert.deepEqual(Object.keys(agent).sort(),
            ["lastActivity", "name", "retireNote", "retiredAt", "retiredBy", "unread", "wake"].sort());
        }
      }
      if (!page.hasMore) { assert.equal(page.nextAfterName, undefined); break; }
      assert.equal(page.nextAfterName, page.agents.at(-1).name);
      afterName = page.nextAfterName;
      assert.ok(pages < 100);
    }
    assert.ok(pages > 1, "the small budget forced several pages");
    assert.deepEqual(seen, ["alpha", "beta", ...Array.from({ length: 30 }, (_, i) => `old-${String(i).padStart(2, "0")}`)]);
    assert.match(errorText(await client.callTool({ name: "bridge_agents",
      arguments: { includeRetired: true, afterName: "nobody" } })), /nobody/);
  } finally {
    await client.close();
  }
});

test("a plain bridge_agents call is never paged and keeps every field (D223)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-agents-plain-"));
  const dbPath = join(dir, "bridge.sqlite");
  const store = new BridgeStore(dbPath);
  for (let index = 0; index < 60; index += 1) {
    store.register(`active-${String(index).padStart(2, "0")}`, Array.from({ length: 20 }, (_, i) => `cap-${i}-${"y".repeat(30)}`));
  }
  store.close();
  const client = await connect(dbPath);
  try {
    const plain = payload(await client.callTool({ name: "bridge_agents", arguments: {} }));
    assert.equal(plain.count, 60);
    assert.equal(plain.agents.length, 60);
    assert.equal(plain.hasMore, false);
    assert.ok(JSON.stringify(plain).length > 48_000, "past the default budget, still whole");
    assert.ok(Array.isArray(plain.agents[0].capabilities));
    assert.ok("presence" in plain.agents[0]);
  } finally {
    await client.close();
  }
});

test("any caller may read a message's status by id (D224)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-status-open-"));
  const dbPath = join(dir, "bridge.sqlite");
  const parties = await connect(dbPath);
  const third = await connect(dbPath);
  try {
    for (const agent of ["asker", "helper"]) await parties.callTool({ name: "bridge_register", arguments: { agent } });
    await third.callTool({ name: "bridge_register", arguments: { agent: "observer" } });
    const sent = payload(await parties.callTool({ name: "bridge_send",
      arguments: { from: "asker", to: "helper", body: "q", expectsReply: true, wake: false } }));
    const status = payload(await third.callTool({ name: "bridge_wake_status", arguments: { messageId: sent.id } }));
    assert.equal(status.message.id, sent.id);
    assert.equal(status.outcome, "pending");
    assert.match(errorText(await third.callTool({ name: "bridge_wake_status", arguments: { messageId: 999999 } })),
      /No message #999999/);
  } finally {
    await parties.close();
    await third.close();
  }
});

/** A ChatGPT app socket under `home` that completes the handshake and never answers about any thread (D226). */
async function silentApp(home: string): Promise<Server> {
  const dir = join(home, ".codex", "ipc");
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  chmodSync(join(home, ".codex"), 0o700);
  const path = join(dir, "ipc.sock");
  const server = createServer(socket => {
    let buffer = Buffer.alloc(0);
    socket.on("error", () => {});
    socket.on("data", chunk => {
      buffer = Buffer.concat([buffer, chunk]);
      while (buffer.length >= 4) {
        const size = buffer.readUInt32LE(0);
        if (buffer.length < size + 4) return;
        const r = JSON.parse(buffer.subarray(4, size + 4).toString());
        buffer = buffer.subarray(size + 4);
        if (r.method !== "initialize") continue;
        const body = Buffer.from(JSON.stringify({ type: "response", requestId: r.requestId, resultType: "success",
          result: { clientId: "test-client" } }));
        const header = Buffer.alloc(4); header.writeUInt32LE(body.length);
        socket.write(Buffer.concat([header, body]));
      }
    });
  });
  await new Promise<void>(ok => server.listen(path, ok));
  chmodSync(path, 0o600);
  return server;
}

test("bridge_agents and bridge_send wait at most 2 s for a silent ChatGPT app (D226)", { skip: process.platform !== "darwin" }, async () => {
  const home = mkdtempSync("/tmp/ar-");
  const app = await silentApp(home);
  const dbPath = join(home, "bridge.sqlite");
  const store = new BridgeStore(dbPath);
  store.register("sender");
  store.register("codex-task", [], { app: "codex", sessionId: "not-opened-task" });
  store.close();
  const client = await connect(dbPath, { HOME: home });
  try {
    let started = Date.now();
    const listing = payload(await client.callTool({ name: "bridge_agents", arguments: {} }));
    assert.ok(Date.now() - started < 3000, `bridge_agents took ${Date.now() - started} ms`);
    assert.equal(listing.agents.find((a: { name: string }) => a.name === "codex-task")?.presence?.state, "not-loaded");
    await client.callTool({ name: "bridge_register", arguments: { agent: "sender" } });
    started = Date.now();
    payload(await client.callTool({ name: "bridge_send",
      arguments: { from: "sender", to: "codex-task", body: "hi", wake: false } }));
    assert.ok(Date.now() - started < 3000, `bridge_send took ${Date.now() - started} ms`);
  } finally {
    await client.close();
    await new Promise<void>(ok => app.close(() => ok()));
    rmSync(home, { recursive: true, force: true });
  }
});
