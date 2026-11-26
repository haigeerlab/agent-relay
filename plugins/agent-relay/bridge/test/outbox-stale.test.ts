import assert from "node:assert/strict";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";

// outbox-stale-filter D294-D296: expired delivery and retired recipients are stale only in the normal listing.
test("outbox hides stale entries by default and counts every matching hidden entry", () => {
  const store = new BridgeStore(":memory:");
  for (const agent of ["sender", "active", "expired", "retired", "reactivated"]) store.register(agent);
  const active = store.send({ fromAgent: "sender", toAgent: "active", body: "active", wake: false, expectsReply: true });
  const expired = store.send({ fromAgent: "sender", toAgent: "expired", body: "expired", wake: false });
  const unknown = store.send({ fromAgent: "sender", toAgent: "unknown", body: "unknown", wake: false });
  store.database.prepare("UPDATE messages SET delivery_state = 'expired' WHERE id = ?").run(expired.id);
  store.retire("retired", { by: "operator" });
  const retired = store.send({ fromAgent: "sender", toAgent: "retired", body: "retired", wake: false });
  store.retire("reactivated", { by: "operator" });
  store.register("reactivated");
  const reactivated = store.send({ fromAgent: "sender", toAgent: "reactivated", body: "reactivated", wake: false });

  const normal = store.outbox("sender");
  assert.deepEqual(normal.entries.map((entry) => entry.id).sort((a, b) => a - b), [active.id, unknown.id, reactivated.id].sort((a, b) => a - b));
  assert.equal(normal.hiddenStale, 2);

  store.ack("retired", [retired.id]);
  const acknowledged = store.outbox("sender", { includeAcknowledged: true });
  assert.equal(acknowledged.hiddenStale, 2, "an acknowledged retired entry remains stale");

  const limited = store.outbox("sender", { includeAcknowledged: true, limit: 1 });
  assert.equal(limited.entries.length, 1);
  assert.equal(limited.hasMore, true);
  assert.equal(limited.hiddenStale, 2);

  const all = store.outbox("sender", { includeStale: true, includeAcknowledged: true });
  assert.deepEqual(all.entries.map((entry) => entry.id).sort((a, b) => a - b),
    [active.id, expired.id, retired.id, reactivated.id, unknown.id].sort((a, b) => a - b));
  assert.equal("hiddenStale" in all, false);
  const byId = new Map(all.entries.map((entry) => [entry.id, entry]));
  assert.equal(byId.get(expired.id)?.deliveryState, "expired");
  assert.equal(byId.get(expired.id)?.recipient, "active");
  assert.equal(byId.get(retired.id)?.recipient, "retired");
  assert.equal(byId.get(unknown.id)?.recipient, "unknown");
  assert.equal(byId.get(reactivated.id)?.recipient, "active");
  // Entries that are listed either way are identical field for field.
  const plain = store.outbox("sender", { includeAcknowledged: true });
  for (const entry of plain.entries) assert.deepEqual(byId.get(entry.id), entry);

  const awaiting = store.outbox("sender", { awaitingReply: true });
  assert.deepEqual(store.outbox("sender", { awaitingReply: true, includeStale: true }), awaiting);
  assert.deepEqual(awaiting.entries.map((entry) => entry.id), [active.id]);
  assert.equal("hiddenStale" in awaiting, false);

  const clean = new BridgeStore(":memory:");
  clean.register("sender");
  clean.register("recipient");
  clean.send({ fromAgent: "sender", toAgent: "recipient", body: "live", wake: false });
  assert.equal("hiddenStale" in clean.outbox("sender"), false);
  clean.close();
  store.close();
});
