// agent-relay idempotency (D33, D34): one retry key means one message.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

import { BridgeStore } from "../src/bridge-store.js";
import { IdempotencyConflictError } from "../src/idempotency.js";

function fresh(): BridgeStore {
  const s = new BridgeStore(":memory:");
  for (const name of ["s", "x", "y"]) s.register(name);
  return s;
}

function jobs(s: BridgeStore): number {
  return Number((s.database.prepare("SELECT COUNT(*) AS n FROM wake_jobs").get() as { n: number }).n);
}

const base = { fromAgent: "s", toAgent: "x", body: "do the thing", threadId: "t1", idempotencyKey: "k" };

test("an identical retry returns the stored message as a duplicate and queues no second ping", () => {
  const s = fresh();
  s.wakes.bind("x", { app: "codex", sessionId: "thread-x" });
  const first = s.deliver(base);
  assert.equal(first.duplicate, false);
  const again = s.deliver(base);
  assert.equal(again.duplicate, true);
  assert.equal(again.message.id, first.message.id);
  assert.equal(jobs(s), 1);
  assert.equal(s.send(base).id, first.message.id, "send() keeps returning the stored message");
  s.close();
});

test("the same key with a different recipient, body or thread is refused and nothing is stored", () => {
  const s = fresh();
  const stored = s.send(base);
  for (const [field, change] of [
    ["toAgent", { toAgent: "y" }],
    ["body", { body: "something else" }],
    ["threadId", { threadId: "t2" }],
    ["threadId", { threadId: null }],
  ] as const) {
    assert.throws(() => s.send({ ...base, ...change }), (error: unknown) => {
      assert.ok(error instanceof IdempotencyConflictError, String(error));
      const text = (error as Error).message;
      assert.match(text, /"k"/);
      assert.match(text, new RegExp(`message #${stored.id}\\b`));
      assert.match(text, /deliveryState: queued/);
      assert.match(text, /already stored/);
      assert.match(text, /no resend is needed/);
      assert.match(text, new RegExp(field));
      return true;
    }, field);
  }
  assert.equal(Number((s.database.prepare("SELECT COUNT(*) AS n FROM messages").get() as { n: number }).n), 1);
  s.close();
});

test("delivery options are not content: wake and timeout changes still return the stored message", () => {
  const s = fresh();
  const stored = s.send(base);
  assert.equal(s.deliver({ ...base, wake: false, expiresInSeconds: 600 }).message.id, stored.id);
  s.close();
});

test("the bridge's own notices keep folding by key, whatever the body", () => {
  const s = fresh();
  const first = s.send({ fromAgent: "bridge", toAgent: "s", body: "failure one", idempotencyKey: "delivery:s->x:1" });
  const second = s.deliver({ fromAgent: "bridge", toAgent: "s", body: "failure two", idempotencyKey: "delivery:s->x:1" });
  assert.equal(second.message.id, first.id);
  assert.equal(second.duplicate, true);
  s.close();
});

test("a retry at the pending cap still returns the stored message, a conflicting one is refused as a conflict", () => {
  process.env.BRIDGE_MAX_PENDING_PER_RECIPIENT = "10";
  try {
    const s = fresh();
    for (let i = 0; i < 10; i += 1) s.send({ fromAgent: "s", toAgent: "x", body: `m${i}`, idempotencyKey: `k${i}` });
    assert.equal(s.deliver({ fromAgent: "s", toAgent: "x", body: "m0", idempotencyKey: "k0" }).duplicate, true);
    assert.throws(() => s.send({ fromAgent: "s", toAgent: "x", body: "changed", idempotencyKey: "k0" }), IdempotencyConflictError);
    s.close();
  } finally {
    delete process.env.BRIDGE_MAX_PENDING_PER_RECIPIENT;
  }
});

test("bridge_send reports a duplicate and returns the refusal text to the sender", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-idempotency-"));
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ["--import", "tsx", "src/server.ts"],
    cwd: dirname(dirname(fileURLToPath(import.meta.url))),
    env: { PATH: process.env.PATH ?? "", HOME: dir, BRIDGE_DB_PATH: join(dir, "bridge.sqlite"), BRIDGE_BACKUPS: "0",
      XDG_DATA_HOME: join(dir, "data") },
    stderr: "pipe",
  });
  const client = new Client({ name: "idempotency-client", version: "1.0.0" });
  await client.connect(transport);
  try {
    for (const agent of ["lead", "worker"]) await client.callTool({ name: "bridge_register", arguments: { agent } });
    const send = (body: string) => client.callTool({ name: "bridge_send",
      arguments: { from: "lead", to: "worker", body, idempotencyKey: "result-1" } });
    const text = (result: Awaited<ReturnType<typeof send>>) => (result.content as Array<{ text: string }>)[0]!.text;
    const first = JSON.parse(text(await send("result")));
    assert.equal(first.duplicate, undefined);
    const again = JSON.parse(text(await send("result")));
    assert.equal(again.duplicate, true);
    assert.equal(again.id, first.id);
    assert.match(String(again.warnings), new RegExp(`already stored as message #${first.id}; not sent again`));
    const refused = await send("reworded result");
    assert.equal(refused.isError, true);
    assert.match(text(refused), /no resend is needed/);
  } finally {
    await client.close();
  }
});
