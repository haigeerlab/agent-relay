// agent-relay acceptance-030-gaps D77: what is waiting for Codex, visible from any session (count, senders, ids; never bodies).
// waiting-list-all-hosts D198: for every host (Claude, Codex, none recorded), with the oldest one's time.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { session } from "./support/session.js";

test("waiting counts unacknowledged, live direct messages for every host, oldest first", () => {
  const store = new BridgeStore(join(mkdtempSync(join(tmpdir(), "agent-relay-waiting-")), "bridge.sqlite"));
  store.register("a");
  store.register("b");
  store.register("cx", [], { app: "codex", sessionId: "thread-cx" });
  store.register("cl", [], { app: "claude", sessionId: "claude-cl" });
  store.register("none");
  const first = store.send({ fromAgent: "a", toAgent: "cx", body: "one" });
  const acked = store.send({ fromAgent: "a", toAgent: "cx", body: "two" });
  const failed = store.send({ fromAgent: "b", toAgent: "cx", body: "three" });
  const expired = store.send({ fromAgent: "b", toAgent: "cx", body: "four" });
  const last = store.send({ fromAgent: "b", toAgent: "cx", body: "five" });
  const claude = store.send({ fromAgent: "a", toAgent: "cl", body: "claude" });
  const unhosted = store.send({ fromAgent: "b", toAgent: "none", body: "no host" });
  store.send({ fromAgent: "a", toAgent: "*", body: "broadcast" });
  store.ack("cx", [acked.id]);
  store.database.prepare("UPDATE messages SET delivery_state = 'failed' WHERE id = ?").run(failed.id);
  store.database.prepare("UPDATE messages SET delivery_state = 'expired' WHERE id = ?").run(expired.id);
  const waiting = store.waiting();
  assert.deepEqual([...waiting.keys()].sort(), ["cl", "cx", "none"]);
  assert.deepEqual(waiting.get("cx"), { count: 2, from: ["a", "b"], ids: [first.id, last.id], oldestAt: first.createdAt });
  assert.deepEqual(waiting.get("cl"), { count: 1, from: ["a"], ids: [claude.id], oldestAt: claude.createdAt });
  assert.deepEqual(waiting.get("none"), { count: 1, from: ["b"], ids: [unhosted.id], oldestAt: unhosted.createdAt });
  for (let i = 0; i < 25; i++) store.send({ fromAgent: "a", toAgent: "cx", body: `bulk ${i}` });
  const many = store.waiting().get("cx")!;
  assert.equal(many.count, 27);
  assert.equal(many.ids.length, 20, "at most 20 ids");
  assert.equal(many.ids[0], first.id, "oldest first");
  assert.equal(many.oldestAt, first.createdAt);
  store.ack("cl", [claude.id]);
  assert.equal(store.waiting().has("cl"), false, "nothing waits once handled");
  store.retire("cx", { by: "test", closeBacklog: false });
  assert.equal(store.waiting().has("cx"), false, "retired agents are not listed");
  store.close();
});

test("bridge_agents shows waiting for Codex and Claude hosts and never the body", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-waiting-mcp-"));
  const prepared = new BridgeStore(join(dir, "bridge.sqlite"));
  prepared.register("sender");
  prepared.register("cx", [], { app: "codex", sessionId: "thread-cx" });
  prepared.register("cl", [], { app: "claude", sessionId: "claude-cl" });
  const message = prepared.send({ fromAgent: "sender", toAgent: "cx", body: "secret body" });
  const toClaude = prepared.send({ fromAgent: "sender", toAgent: "cl", body: "secret claude body" });
  prepared.close();
  const client = await session(dir, "claude-viewer");
  try {
    const result = await client.call("bridge_agents", {});
    const agents = result.json().agents;
    assert.deepEqual(agents.find((a: any) => a.name === "cx").waiting,
      { count: 1, from: ["sender"], ids: [message.id], oldestAt: message.createdAt });
    assert.deepEqual(agents.find((a: any) => a.name === "cl").waiting,
      { count: 1, from: ["sender"], ids: [toClaude.id], oldestAt: toClaude.createdAt });
    assert.equal(agents.find((a: any) => a.name === "sender").waiting, undefined);
    assert.doesNotMatch(result.text, /secret/);
  } finally {
    await client.close();
  }
});
