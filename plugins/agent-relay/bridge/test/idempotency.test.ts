// agent-relay idempotency (D33, D34): one retry key means one message.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

import { spawn } from "node:child_process";

import { BridgeStore } from "../src/bridge-store.js";
import { transition } from "../src/delivery.js";
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
    const reply = JSON.parse(text(await client.callTool({ name: "bridge_send",
      arguments: { from: "worker", to: "lead", body: "thanks", replyTo: first.id } })));
    assert.equal(reply.replyTo, first.id);
  } finally {
    await client.close();
  }
});

// agent-relay idempotency: the reply link (assumption 3, D36).
test("a reply names an existing original and takes its thread; a different thread or unknown original is refused", () => {
  const s = fresh();
  const original = s.send({ fromAgent: "s", toAgent: "x", body: "please review", threadId: "t1" });
  const reply = s.send({ fromAgent: "x", toAgent: "s", body: "done", replyTo: original.id });
  assert.equal(reply.replyTo, original.id);
  assert.equal(reply.threadId, "t1", "thread inherited");
  assert.equal(s.send({ fromAgent: "x", toAgent: "s", body: "more", replyTo: original.id, threadId: "t1" }).threadId, "t1");
  assert.throws(() => s.send({ fromAgent: "x", toAgent: "s", body: "elsewhere", replyTo: original.id, threadId: "t2" }),
    new RegExp(`Message #${original.id} is on thread "t1".*not "t2"`));
  assert.throws(() => s.send({ fromAgent: "x", toAgent: "s", body: "lost", replyTo: 9999 }), /No message #9999 to reply to/);
  const unthreaded = s.send({ fromAgent: "s", toAgent: "x", body: "no thread" });
  assert.throws(() => s.send({ fromAgent: "x", toAgent: "s", body: "r", replyTo: unthreaded.id, threadId: "t9" }), /no thread/);
  assert.equal(s.send({ fromAgent: "x", toAgent: "s", body: "r", replyTo: unthreaded.id }).threadId, null);
  s.close();
});

test("the reply link is part of a retry's content", () => {
  const s = fresh();
  const a = s.send({ fromAgent: "s", toAgent: "x", body: "a" });
  const b = s.send({ fromAgent: "s", toAgent: "x", body: "b" });
  s.send({ fromAgent: "x", toAgent: "s", body: "ok", replyTo: a.id, idempotencyKey: "r" });
  assert.throws(() => s.send({ fromAgent: "x", toAgent: "s", body: "ok", replyTo: b.id, idempotencyKey: "r" }),
    (error: unknown) => error instanceof IdempotencyConflictError && /replyTo/.test((error as Error).message));
  assert.equal(s.deliver({ fromAgent: "x", toAgent: "s", body: "ok", replyTo: a.id, idempotencyKey: "r" }).duplicate, true);
  s.close();
});

test("inbox, thread and outbox show the link; the outbox lists each message's replies", () => {
  const s = fresh();
  const original = s.send({ fromAgent: "s", toAgent: "x", body: "question", threadId: "t1" });
  const first = s.send({ fromAgent: "x", toAgent: "s", body: "answer 1", replyTo: original.id });
  const second = s.send({ fromAgent: "y", toAgent: "s", body: "answer 2", replyTo: original.id });
  assert.deepEqual(s.inbox("s").map((m) => m.replyTo), [original.id, original.id]);
  assert.deepEqual(s.thread("t1").map((m) => m.replyTo), [null, original.id, original.id]);
  const sent = s.outbox("s").entries.find((entry) => entry.id === original.id);
  assert.equal(sent?.replyTo, null);
  assert.deepEqual(sent?.replies, [first.id, second.id]);
  const answered = s.outbox("x").entries.find((entry) => entry.id === first.id);
  assert.equal(answered?.replyTo, original.id);
  assert.deepEqual(answered?.replies, []);
  s.close();
});

// agent-relay idempotency: reply de-duplication (D35).
test("the same reply to the same message is stored once; a different body or recipient is a new reply", () => {
  const s = fresh();
  s.wakes.bind("s", { app: "codex", sessionId: "thread-s" });
  const original = s.send({ fromAgent: "s", toAgent: "x", body: "question", threadId: "t1" });
  const first = s.deliver({ fromAgent: "x", toAgent: "s", body: "answer", replyTo: original.id });
  const again = s.deliver({ fromAgent: "x", toAgent: "s", body: "answer", replyTo: original.id, idempotencyKey: "fresh" });
  assert.equal(again.duplicate, true);
  assert.equal(again.message.id, first.message.id);
  assert.equal(jobs(s), 1, "no second ping");
  assert.equal(s.deliver({ fromAgent: "x", toAgent: "s", body: "answer, amended", replyTo: original.id }).duplicate, false);
  assert.equal(s.deliver({ fromAgent: "y", toAgent: "s", body: "answer", replyTo: original.id }).duplicate, false);
  assert.equal(s.deliver({ fromAgent: "x", toAgent: "y", body: "answer", replyTo: original.id }).duplicate, false);
  s.close();
});

test("a reply that expired or failed may be sent again", () => {
  const s = fresh();
  const original = s.send({ fromAgent: "s", toAgent: "x", body: "question" });
  const expired = s.send({ fromAgent: "x", toAgent: "s", body: "answer", replyTo: original.id });
  s.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1, expired.id);
  const second = s.deliver({ fromAgent: "x", toAgent: "s", body: "answer", replyTo: original.id });
  assert.equal(second.duplicate, false);
  assert.equal(s.messageById(expired.id)?.deliveryState, "expired");
  transition(s.database, second.message.id, "sending");
  transition(s.database, second.message.id, "failed");
  const third = s.deliver({ fromAgent: "x", toAgent: "s", body: "answer", replyTo: original.id });
  assert.equal(third.duplicate, false);
  assert.equal(s.deliver({ fromAgent: "x", toAgent: "s", body: "answer", replyTo: original.id }).message.id, third.message.id);
  s.close();
});

test("processes racing the same reply on one mailbox store it once", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-reply-race-"));
  const path = join(dir, "bridge.sqlite");
  const setup = new BridgeStore(path);
  const original = setup.send({ fromAgent: "s", toAgent: "x", body: "question" });
  setup.close();
  // Every process opens first and sends at one shared instant, so the sends themselves race. (Opening while another
  // process writes can fail with "database is locked": the store sets busy_timeout after journal_mode — upstream.)
  const start = Date.now() + 1500;
  const script = `const { BridgeStore } = await import("./src/bridge-store.ts");
    const s = new BridgeStore(${JSON.stringify(path)});
    await new Promise((resolve) => setTimeout(resolve, ${start} - Date.now()));
    console.log(s.deliver({ fromAgent: "x", toAgent: "s", body: "answer", replyTo: ${original.id} }).message.id);
    s.close();`;
  const cwd = dirname(dirname(fileURLToPath(import.meta.url)));
  const ids = await Promise.all(Array.from({ length: 4 }, () => new Promise<string>((resolve, reject) => {
    const child = spawn(process.execPath, ["--import", "tsx", "--input-type=module", "-e", script], { cwd });
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => { out += chunk; });
    child.stderr.on("data", (chunk) => { err += chunk; });
    child.on("close", (code) => (code === 0 ? resolve(out.trim()) : reject(new Error(err))));
  })));
  assert.equal(new Set(ids).size, 1, ids.join(","));
  const check = new BridgeStore(path);
  assert.equal(Number((check.database.prepare("SELECT COUNT(*) AS n FROM messages WHERE reply_to = ?").get(original.id) as { n: number }).n), 1);
  check.close();
});
