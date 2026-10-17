// agent-relay awaiting-reply-view (D201–D204): requests marked expectsReply, and who waits for whose answer.
import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, rmSync } from "node:fs";
import { createServer, type Server } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

import { AWAITING_PRESENCE_TIMEOUT_MS, CODEX_NO_ANSWER_SHORT, awaitingCodexPresence, pagePresence }
  from "../src/awaiting-reply.js";
import { BridgeStore } from "../src/bridge-store.js";
import { transition } from "../src/delivery.js";
import { IdempotencyConflictError } from "../src/idempotency.js";
import type { Presence } from "../src/presence.js";
import { SCHEMA_VERSION } from "../src/schema.js";
import type { WakeTarget } from "../src/wake-queue.js";

function fresh(): BridgeStore {
  const s = new BridgeStore(":memory:");
  for (const name of ["asker", "helper", "other"]) s.register(name);
  return s;
}

test("schema 6 adds messages.expects_reply; rows from an older schema read as unmarked", () => {
  assert.ok(SCHEMA_VERSION >= 6);
  const dir = mkdtempSync(join(tmpdir(), "bridge-v5-v6-"));
  const path = join(dir, "bridge.sqlite");
  const first = new BridgeStore(path, { backupDir: join(dir, "backups") });
  first.register("asker");
  first.register("helper");
  const old = first.send({ fromAgent: "asker", toAgent: "helper", body: "written before 6" });
  first.close();
  const raw = new DatabaseSync(path);
  raw.exec("ALTER TABLE messages DROP COLUMN expects_reply");
  raw.exec("DROP TABLE IF EXISTS request_closures");
  raw.exec("PRAGMA user_version = 5");
  raw.close();

  const store = new BridgeStore(path, { backupDir: join(dir, "backups") });
  assert.deepEqual(store.migration, { from: 5, to: SCHEMA_VERSION, newer: false });
  assert.equal(store.messageById(old.id)?.expectsReply, false);
  store.close();
});

test("a send stores expectsReply; without it a message is unmarked", () => {
  const s = fresh();
  const marked = s.send({ fromAgent: "asker", toAgent: "helper", body: "what is the port?", expectsReply: true });
  const plain = s.send({ fromAgent: "asker", toAgent: "helper", body: "fyi: deployed" });
  assert.equal(s.messageById(marked.id)?.expectsReply, true);
  assert.equal(marked.expectsReply, true);
  assert.equal(s.messageById(plain.id)?.expectsReply, false);
  s.close();
});

test("a broadcast cannot be marked expectsReply (D201)", () => {
  const s = fresh();
  assert.throws(() => s.send({ fromAgent: "asker", toAgent: "*", body: "anyone?", expectsReply: true }),
    /broadcast.*expectsReply|expectsReply.*broadcast/i);
  assert.equal(Number((s.database.prepare("SELECT COUNT(*) AS n FROM messages").get() as { n: number }).n), 0);
  s.close();
});

test("a reply may itself be marked: it answers the original and opens a new request (D201)", () => {
  const s = fresh();
  const question = s.send({ fromAgent: "asker", toAgent: "helper", body: "port?", expectsReply: true });
  const followUp = s.send({ fromAgent: "helper", toAgent: "asker", body: "which service?", replyTo: question.id,
    expectsReply: true });
  assert.equal(followUp.replyTo, question.id);
  assert.equal(followUp.expectsReply, true);
  s.close();
});

test("a retry with the same key and a different expectsReply is refused like any content change (D201)", () => {
  const s = fresh();
  const base = { fromAgent: "asker", toAgent: "helper", body: "port?", idempotencyKey: "k1" };
  const stored = s.send({ ...base, expectsReply: true });
  assert.equal(s.deliver({ ...base, expectsReply: true }).duplicate, true);
  assert.throws(() => s.send({ ...base, expectsReply: false }), (error: unknown) => {
    assert.ok(error instanceof IdempotencyConflictError, String(error));
    assert.match((error as Error).message, new RegExp(`message #${stored.id}\\b`));
    assert.match((error as Error).message, /expectsReply/);
    return true;
  });
  assert.throws(() => s.send(base), IdempotencyConflictError, "omitted means false, which differs too");
  s.close();
});

// ---- Task 2: the asking view, bridge_outbox awaitingReply (D202, D203) ----

function awaiting(s: BridgeStore, agent = "asker", options: { limit?: number; now?: number } = {}) {
  return s.outbox(agent, { awaitingReply: true, ...options });
}

test("a marked request stays open until a linked reply, also after the recipient acked it (D202)", () => {
  const s = fresh();
  const question = s.send({ fromAgent: "asker", toAgent: "helper", body: "port?", expectsReply: true });
  s.send({ fromAgent: "asker", toAgent: "helper", body: "fyi" });
  assert.deepEqual(awaiting(s).entries.map((entry) => entry.id), [question.id], "an unmarked message never appears");
  s.ack("helper", [question.id]);
  assert.deepEqual(awaiting(s).entries.map((entry) => entry.id), [question.id], "an acknowledgement is not an answer");
  assert.equal(s.outbox("asker").entries.length, 1, "the default view still hides acknowledged messages");
  s.send({ fromAgent: "helper", toAgent: "asker", body: "8080", replyTo: question.id });
  assert.deepEqual(awaiting(s).entries, []);
  assert.equal(awaiting(s).totalAwaitingReply, 0);
  s.close();
});

test("failed, expired and retired-recipient requests leave the view (D202)", () => {
  const s = fresh();
  const failed = s.send({ fromAgent: "asker", toAgent: "helper", body: "a", expectsReply: true });
  const expired = s.send({ fromAgent: "asker", toAgent: "helper", body: "b", expectsReply: true });
  const toRetired = s.send({ fromAgent: "asker", toAgent: "other", body: "c", expectsReply: true });
  const open = s.send({ fromAgent: "asker", toAgent: "helper", body: "d", expectsReply: true });
  transition(s.database, failed.id, "sending");
  transition(s.database, failed.id, "failed");
  transition(s.database, expired.id, "expired");
  s.retire("other", { by: "user" });
  assert.deepEqual(awaiting(s).entries.map((entry) => entry.id), [open.id]);
  assert.ok(toRetired.id > 0);
  s.close();
});

test("oldest first, waitingSeconds from the read time, totalAwaitingReply beyond the page (D203)", () => {
  const s = fresh();
  const ids = [1, 2, 3].map((n) => s.send({ fromAgent: "asker", toAgent: "helper", body: `q${n}`, expectsReply: true }).id);
  const created = Date.parse(s.messageById(ids[0] as number)?.createdAt as string);
  const page = awaiting(s, "asker", { limit: 2, now: created + 90_500 });
  assert.deepEqual(page.entries.map((entry) => entry.id), ids.slice(0, 2));
  assert.equal(page.totalAwaitingReply, 3);
  assert.equal(page.hasMore, true);
  assert.equal(page.entries[0]?.waitingSeconds, 90);
  assert.equal(page.entries[0]?.expectsReply, true);
  s.close();
});

test("every outbox entry says whether it expects a reply; only the awaiting view has waitingSeconds", () => {
  const s = fresh();
  s.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  s.send({ fromAgent: "asker", toAgent: "helper", body: "fyi" });
  const normal = s.outbox("asker");
  assert.deepEqual(normal.entries.map((entry) => entry.expectsReply), [false, true]);
  assert.equal(normal.entries[0]?.waitingSeconds, undefined);
  assert.equal(normal.totalAwaitingReply, 1);
  s.close();
});

test("presence is read once per distinct recipient on the page, never for a retired or hostless one (D203)", async () => {
  const asked: string[] = [];
  const lookup = async (host: WakeTarget): Promise<Presence> => {
    asked.push(host.sessionId);
    return { state: "running" };
  };
  const hosts = new Map<string, { host: WakeTarget | null; retired: boolean }>([
    ["helper", { host: { app: "claude", sessionId: "s-helper" }, retired: false }],
    ["other", { host: { app: "codex", sessionId: "t-other" }, retired: true }],
    ["ghost", { host: null, retired: false }],
  ]);
  const result = await pagePresence(["helper", "helper", "other", "ghost", "helper"], (name) => hosts.get(name), lookup);
  assert.deepEqual(asked, ["s-helper"]);
  assert.deepEqual(result.get("helper"), { state: "running" });
  assert.equal(result.has("other"), false, "a retired recipient gets no presence");
  assert.deepEqual(result.get("ghost"), { state: "unknown", detail: "no recorded host session" });
  assert.equal((await pagePresence([], () => undefined, lookup)).size, 0);
  assert.equal(asked.length, 1);
});

/** A Codex app that completes the handshake and never answers about any thread. */
async function silentCodex(): Promise<{ path: string; server: Server; dir: string }> {
  const dir = mkdtempSync(join(tmpdir(), "codex-silent-"));
  chmodSync(dir, 0o700);
  const path = join(dir, "ipc.sock");
  const server = createServer((socket) => {
    let buffer = Buffer.alloc(0);
    socket.on("error", () => {});
    socket.on("data", (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      while (buffer.length >= 4) {
        const size = buffer.readUInt32LE(0);
        if (buffer.length < size + 4) return;
        const request = JSON.parse(buffer.subarray(4, size + 4).toString());
        buffer = buffer.subarray(size + 4);
        if (request.method !== "initialize") continue;
        const body = Buffer.from(JSON.stringify({ type: "response", requestId: request.requestId,
          resultType: "success", result: { clientId: "test-client" } }));
        const header = Buffer.alloc(4); header.writeUInt32LE(body.length);
        socket.write(Buffer.concat([header, body]));
      }
    });
  });
  await new Promise<void>((ok) => server.listen(path, ok));
  chmodSync(path, 0o600);
  return { path, server, dir };
}

test("a silent Codex recipient costs about 2 s and reads unknown with the short detail (D203)", { skip: process.platform === "win32" }, async () => {
  assert.equal(AWAITING_PRESENCE_TIMEOUT_MS, 2000);
  const fake = await silentCodex();
  try {
    const started = Date.now();
    const presence = await awaitingCodexPresence("not-opened-task", fake.path);
    const elapsed = Date.now() - started;
    assert.deepEqual(presence, { state: "unknown", detail: CODEX_NO_ANSWER_SHORT });
    assert.match(CODEX_NO_ANSWER_SHORT, /within 2 s/);
    assert.match(CODEX_NO_ANSWER_SHORT, /not opened since the app started/);
    assert.ok(elapsed >= 1900 && elapsed < 4000, `took ${elapsed} ms`);
  } finally {
    await new Promise<void>((ok) => fake.server.close(() => ok()));
    rmSync(fake.dir, { recursive: true, force: true });
  }
});

test("a missing Codex socket stays unknown with the usual detail, at once", { skip: process.platform === "win32" }, async () => {
  const presence = await awaitingCodexPresence("t", join(tmpdir(), "no-such-dir-awaiting", "ipc.sock"));
  assert.deepEqual(presence, { state: "unknown", detail: "the Codex app cannot be asked" });
});

// ---- Task 3: the asked view, bridge_agents owesReplies (D204) ----

test("owesReplies lists, per recipient, the open requests addressed to it, oldest first, at most 20 ids", () => {
  const s = fresh();
  const first = s.send({ fromAgent: "asker", toAgent: "helper", body: "q0", expectsReply: true });
  const rest = Array.from({ length: 21 }, (_, n) =>
    s.send({ fromAgent: n % 2 ? "other" : "asker", toAgent: "helper", body: `q${n + 1}`, expectsReply: true }).id);
  s.send({ fromAgent: "helper", toAgent: "asker", body: "fyi" });
  s.ack("helper", [first.id]);
  const owes = s.owesReplies();
  assert.deepEqual([...owes.keys()], ["helper"], "an agent with nothing open has no entry; unmarked messages count nothing");
  const helper = owes.get("helper");
  assert.equal(helper?.count, 22, "an acknowledged request is still owed");
  assert.equal(helper?.ids.length, 20);
  assert.deepEqual(helper?.ids.slice(0, 2), [first.id, rest[0]]);
  assert.equal(helper?.oldestAt, first.createdAt);
  s.close();
});

test("a reply, an expiry or the recipient's retirement removes a request from owesReplies", () => {
  const s = fresh();
  const answered = s.send({ fromAgent: "asker", toAgent: "helper", body: "a", expectsReply: true });
  const expired = s.send({ fromAgent: "asker", toAgent: "helper", body: "b", expectsReply: true });
  s.send({ fromAgent: "asker", toAgent: "other", body: "c", expectsReply: true });
  s.send({ fromAgent: "helper", toAgent: "asker", body: "done", replyTo: answered.id });
  transition(s.database, expired.id, "expired");
  s.retire("other", { by: "user" });
  assert.equal(s.owesReplies().size, 0);
  s.close();
});

// ---- through MCP ----

async function withServer(run: (call: (name: string, args: Record<string, unknown>) => Promise<{ data: any; isError: boolean; text: string }>) => Promise<void>): Promise<void> {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-awaiting-"));
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ["--import", "tsx", "src/server.ts"],
    cwd: dirname(dirname(fileURLToPath(import.meta.url))),
    env: { PATH: process.env.PATH ?? "", HOME: dir, BRIDGE_DB_PATH: join(dir, "bridge.sqlite"), BRIDGE_BACKUPS: "0",
      XDG_DATA_HOME: join(dir, "data") },
    stderr: "pipe",
  });
  const client = new Client({ name: "awaiting-client", version: "1.0.0" });
  await client.connect(transport);
  try {
    assert.match(client.getInstructions() ?? "", /expectsReply: true is a request: when done, answer it with bridge_send replyTo/);
    // codex-identity-recovery D209, D210: the same server instructions tell sessions how to recover.
    assert.match(client.getInstructions() ?? "", /recorded for a Codex task, register that name again as the refusal says and repeat the call/);
    assert.match(client.getInstructions() ?? "", /Transport closed, stop retrying and ask the user to reopen the app/);
    // request-closing D217, D219, D222: and how to close several requests or withdraw one.
    assert.match(client.getInstructions() ?? "", /name the others in alsoAnswers; withdraw your own requests you no longer need with withdraws; after either, trust closed/);
    await run(async (name, args) => {
      const result = await client.callTool({ name, arguments: args });
      const text = (result.content as Array<{ text: string }>)[0]!.text;
      const isError = result.isError === true;
      return { data: isError ? null : JSON.parse(text), isError, text };
    });
  } finally {
    await client.close();
  }
}

test("bridge_send takes expectsReply and bridge_outbox awaitingReply lists the open request with presence", async () => {
  await withServer(async (call) => {
    for (const agent of ["lead", "worker"]) await call("bridge_register", { agent });
    const sent = await call("bridge_send", { from: "lead", to: "worker", body: "port?", expectsReply: true });
    assert.equal(sent.data.expectsReply, true);
    const broadcast = await call("bridge_send", { from: "lead", to: "*", body: "anyone?", expectsReply: true });
    assert.equal(broadcast.isError, true);
    assert.match(broadcast.text, /broadcast cannot carry expectsReply/);
    const view = (await call("bridge_outbox", { agent: "lead", awaitingReply: true })).data;
    assert.equal(view.totalAwaitingReply, 1);
    assert.deepEqual(view.entries.map((entry: { id: number }) => entry.id), [sent.data.id]);
    assert.equal(typeof view.entries[0].waitingSeconds, "number");
    assert.deepEqual(view.entries[0].recipientPresence, { state: "unknown", detail: "no recorded host session" });
    const inbox = (await call("bridge_inbox", { agent: "worker" })).data;
    assert.equal(inbox.messages[0].expectsReply, true, "the recipient sees that an answer is expected");
    const agents = (await call("bridge_agents", {})).data.agents as Array<{ name: string; owesReplies?: unknown }>;
    assert.deepEqual(agents.find((agent) => agent.name === "worker")?.owesReplies,
      { count: 1, ids: [sent.data.id], oldestAt: sent.data.createdAt });
    assert.equal(agents.find((agent) => agent.name === "lead")?.owesReplies, undefined);
    await call("bridge_send", { from: "worker", to: "lead", body: "8080", replyTo: sent.data.id });
    assert.equal((await call("bridge_outbox", { agent: "lead", awaitingReply: true })).data.totalAwaitingReply, 0);
    const plain = (await call("bridge_outbox", { agent: "lead" })).data;
    assert.equal(plain.entries[0].recipientPresence, undefined, "the normal view looks up no presence");
  });
});

// agent-relay reply-own-message-guidance D211: the sender adds to its request as the refusal says; that is not an
// answer, so the request stays open.
test("a sender's addendum on the thread leaves its own request open (D211)", () => {
  const s = fresh();
  const question = s.send({ fromAgent: "asker", toAgent: "helper", body: "port?", threadId: "t", expectsReply: true });
  assert.throws(() => s.send({ fromAgent: "asker", toAgent: "helper", body: "also host?", replyTo: question.id }),
    /with threadId "t" and without replyTo/);
  s.send({ fromAgent: "asker", toAgent: "helper", body: "also host?", threadId: "t" });
  assert.deepEqual(awaiting(s).entries.map((entry) => entry.id), [question.id]);
  s.close();
});
