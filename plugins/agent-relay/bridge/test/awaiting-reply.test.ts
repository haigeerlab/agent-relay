// agent-relay awaiting-reply-view (D201–D204): requests marked expectsReply, and who waits for whose answer.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { IdempotencyConflictError } from "../src/idempotency.js";
import { SCHEMA_VERSION } from "../src/schema.js";

function fresh(): BridgeStore {
  const s = new BridgeStore(":memory:");
  for (const name of ["asker", "helper", "other"]) s.register(name);
  return s;
}

test("schema 6 adds messages.expects_reply; rows from an older schema read as unmarked", () => {
  assert.equal(SCHEMA_VERSION, 6);
  const dir = mkdtempSync(join(tmpdir(), "bridge-v5-v6-"));
  const path = join(dir, "bridge.sqlite");
  const first = new BridgeStore(path, { backupDir: join(dir, "backups") });
  first.register("asker");
  first.register("helper");
  const old = first.send({ fromAgent: "asker", toAgent: "helper", body: "written before 6" });
  first.close();
  const raw = new DatabaseSync(path);
  raw.exec("ALTER TABLE messages DROP COLUMN expects_reply");
  raw.exec("PRAGMA user_version = 5");
  raw.close();

  const store = new BridgeStore(path, { backupDir: join(dir, "backups") });
  assert.deepEqual(store.migration, { from: 5, to: 6, newer: false });
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
