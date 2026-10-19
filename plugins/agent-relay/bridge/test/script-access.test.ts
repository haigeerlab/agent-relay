// agent-relay script-access (D240–D245): scripts read the mailbox read-only and send as a script identity.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";

function mailbox(): string {
  const dir = mkdtempSync(join(tmpdir(), "ar-script-"));
  return join(dir, "bridge.sqlite");
}

// D242: a read-only store never writes, never migrates and never sweeps.
test("a read-only store refuses writes (D242)", () => {
  const path = mailbox();
  const writer = new BridgeStore(path);
  writer.register("asker");
  writer.close();
  const reader = new BridgeStore(path, { readOnly: true });
  assert.equal(reader.readOnly, true);
  assert.equal(reader.agents().length, 1);
  assert.throws(() => reader.register("other"), /readonly|read-only/i);
  reader.close();
});

test("a read-only store does not migrate an older mailbox (D242)", () => {
  const path = mailbox();
  const writer = new BridgeStore(path);
  writer.close();
  const raw = new DatabaseSync(path);
  raw.exec("PRAGMA user_version = 6");
  raw.close();
  assert.throws(() => new BridgeStore(path, { readOnly: true }), /schema 6.*schema 7|upgrade/i);
  const check = new DatabaseSync(path, { readOnly: true });
  assert.equal((check.prepare("PRAGMA user_version").get() as { user_version: number }).user_version, 6);
  check.close();
});

test("a read-only store does not expire an overdue message (D242)", () => {
  const path = mailbox();
  const writer = new BridgeStore(path);
  for (const name of ["asker", "helper"]) writer.register(name);
  const message = writer.send({ fromAgent: "asker", toAgent: "helper", body: "q", expiresInSeconds: 60 });
  const raw = (writer as unknown as { db: DatabaseSync }).db;
  raw.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1000, message.id);
  writer.close();
  const reader = new BridgeStore(path, { readOnly: true });
  assert.equal(reader.outbox("asker", {}).entries.find((e) => e.id === message.id)?.deliveryState, "queued");
  reader.close();
  const normal = new BridgeStore(path);
  assert.equal(normal.outbox("asker", {}).entries.find((e) => e.id === message.id)?.deliveryState, "expired");
  normal.close();
});
