// agent-relay request-closing (D216–D222): one answer closes several requests; a sender withdraws its own.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { SCHEMA_VERSION } from "../src/schema.js";

function fresh(path = ":memory:"): BridgeStore {
  const s = new BridgeStore(path);
  for (const name of ["asker", "twin", "helper", "other"]) s.register(name);
  return s;
}

test("schema 7 adds request_closures; requests from before it have no closure (D216)", () => {
  assert.equal(SCHEMA_VERSION, 7);
  const dir = mkdtempSync(join(tmpdir(), "bridge-v6-v7-"));
  const path = join(dir, "bridge.sqlite");
  const first = fresh(path);
  const old = first.send({ fromAgent: "asker", toAgent: "helper", body: "written before 7", expectsReply: true });
  first.close();
  const raw = new DatabaseSync(path);
  raw.exec("DROP TABLE request_closures");
  raw.exec("PRAGMA user_version = 6");
  raw.close();

  const store = new BridgeStore(path, { backupDir: join(dir, "backups") });
  assert.deepEqual(store.migration, { from: 6, to: 7, newer: false });
  assert.deepEqual(store.owesReplies().get("helper")?.ids, [old.id]);
  store.close();
  const reopened = new BridgeStore(path, { backupDir: join(dir, "backups") });
  assert.deepEqual(reopened.migration, { from: 7, to: 7, newer: false });
  reopened.close();
});

test("a closure row closes a request in every view (D216)", () => {
  const store = fresh();
  const request = store.send({ fromAgent: "asker", toAgent: "helper", body: "please", expectsReply: true });
  assert.equal(store.owesReplies().get("helper")?.count, 1);
  const raw = (store as unknown as { db: DatabaseSync }).db;
  raw.prepare("INSERT INTO request_closures (request_id, message_id, kind, closed_at) VALUES (?, ?, 'withdrawn', ?)")
    .run(request.id, request.id, new Date().toISOString());
  assert.equal(store.owesReplies().get("helper"), undefined);
  assert.equal(store.outbox("asker", { awaitingReply: true }).entries.length, 0);
  store.close();
});
