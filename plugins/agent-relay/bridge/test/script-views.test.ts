// agent-relay script-access D241: the script reads are the MCP tools' own output.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

import { BridgeStore } from "../src/bridge-store.js";
import { agentsView, outboxView } from "../src/views.js";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

async function connect(dbPath: string) {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ["--import", "tsx", "src/server.ts"],
    cwd: projectRoot,
    env: { PATH: process.env.PATH ?? "", HOME: process.env.HOME ?? "", BRIDGE_DB_PATH: dbPath, BRIDGE_BACKUPS: "0",
      XDG_DATA_HOME: join(dirname(dbPath), "data") },
    stderr: "pipe",
  });
  const client = new Client({ name: "views", version: "1.0.0" });
  await client.connect(transport);
  return client;
}

function payload(result: Awaited<ReturnType<Client["callTool"]>>): Record<string, unknown> {
  const first = (result.content as Array<{ type: string; text?: string }>)[0];
  assert.equal(result.isError ?? false, false, first?.text);
  return JSON.parse(first!.text!);
}

test("agentsView and outboxView return what bridge_agents and bridge_outbox return (D241)", async () => {
  const dbPath = join(mkdtempSync(join(tmpdir(), "ar-views-")), "bridge.sqlite");
  const client = await connect(dbPath);
  try {
    for (const agent of ["asker", "helper"]) await client.callTool({ name: "bridge_register", arguments: { agent, wake: null } });
    await client.callTool({ name: "bridge_send", arguments: { from: "asker", to: "helper", body: "q", expectsReply: true } });
    // bridge_outbox records the owner's own activity (lastSeen), so the listing is taken after it.
    const mcpOutbox = payload(await client.callTool({ name: "bridge_outbox", arguments: { agent: "asker" } }));
    const mcpAgents = payload(await client.callTool({ name: "bridge_agents", arguments: {} }));
    const store = new BridgeStore(dbPath, { readOnly: true });
    try {
      assert.deepEqual(await agentsView(store, {}), mcpAgents);
      assert.deepEqual(await outboxView(store, { agent: "asker" }), mcpOutbox);
    } finally {
      store.close();
    }
  } finally {
    await client.close();
  }
});

test("a session cannot register a script identity's name without takeover (D244)", async () => {
  const dbPath = join(mkdtempSync(join(tmpdir(), "ar-views-")), "bridge.sqlite");
  const seed = new BridgeStore(dbPath);
  seed.registerScriptIdentity("di-patrol");
  seed.close();
  const client = await connect(dbPath);
  try {
    const refused = await client.callTool({ name: "bridge_register", arguments: { agent: "di-patrol", wake: null } });
    assert.equal(refused.isError, true);
    assert.match((refused.content as Array<{ text: string }>)[0].text, /script identity/);
  } finally {
    await client.close();
  }
});
