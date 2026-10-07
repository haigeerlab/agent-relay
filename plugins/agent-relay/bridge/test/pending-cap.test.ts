// agent-relay durable-ordering (D30, D31): a recipient may hold at most N undelivered messages.
import assert from "node:assert/strict";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { DEFAULT_MAX_PENDING, maxPendingPerRecipient, pendingWarning, transition } from "../src/delivery.js";

const CAP = 10;

function capped(): BridgeStore {
  process.env.BRIDGE_MAX_PENDING_PER_RECIPIENT = String(CAP);
  const s = new BridgeStore(":memory:");
  for (const name of ["s", "x"]) s.register(name);
  return s;
}

function fill(s: BridgeStore, n: number): number[] {
  return Array.from({ length: n }, (_, i) => s.send({ fromAgent: "s", toAgent: "x", body: `m${i}`, idempotencyKey: `k${i}` }).id);
}

test("the cap defaults to 100 and accepts 10 … 10 000 from the setting", () => {
  assert.equal(DEFAULT_MAX_PENDING, 100);
  assert.equal(maxPendingPerRecipient({}), 100);
  assert.equal(maxPendingPerRecipient({ BRIDGE_MAX_PENDING_PER_RECIPIENT: "250" }), 250);
  for (const bad of ["", "x", "9", "10001"]) assert.equal(maxPendingPerRecipient({ BRIDGE_MAX_PENDING_PER_RECIPIENT: bad }), 100, bad);
});

test("a send over the cap is refused with the recipient, the count and the setting; a retry of a stored one is not", () => {
  const s = capped();
  fill(s, CAP);
  assert.throws(() => s.send({ fromAgent: "s", toAgent: "x", body: "one too many" }),
    /"x" already has 10 undelivered messages.*BRIDGE_MAX_PENDING_PER_RECIPIENT/);
  const again = s.send({ fromAgent: "s", toAgent: "x", body: "m0", idempotencyKey: "k0" });
  assert.equal(again.body, "m0");
  s.send({ fromAgent: "s", toAgent: "*", body: "broadcasts are not counted" });
  s.close();
});

test("expiry, fetch, acknowledgement and failure release capacity; unknown does not", () => {
  const s = capped();
  const ids = fill(s, CAP);
  const free = () => s.send({ fromAgent: "s", toAgent: "x", body: "fits", wake: false });
  const full = () => assert.throws(() => s.send({ fromAgent: "s", toAgent: "x", body: "full", wake: false }), /undelivered/);

  transition(s.database, ids[0], "sending");
  transition(s.database, ids[0], "unknown");
  full();
  s.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1, ids[1]);
  const a = free(); full();
  s.wakes.recordRead("x", [ids[2]]);
  free(); full();
  s.ack("x", [ids[0]]);
  free(); full();
  transition(s.database, ids[3], "sending");
  transition(s.database, ids[3], "failed");
  free(); full();
  assert.ok(a);
  s.close();
});

test("older rows without a state but already acknowledged do not count", () => {
  const s = capped();
  const insert = s.database.prepare("INSERT INTO messages (from_agent, to_agent, body, created_at) VALUES ('s', 'x', 'old', ?)");
  for (let i = 0; i < CAP; i++) {
    const id = Number(insert.run(new Date().toISOString()).lastInsertRowid);
    s.ack("x", [id]);
  }
  s.send({ fromAgent: "s", toAgent: "x", body: "still fits" });
  s.close();
});

test("a send that brings a recipient to 80 % of the cap carries a warning", () => {
  const s = capped();
  fill(s, 7);
  assert.equal(pendingWarning(s.database, "x"), null);
  fill(s, 8);
  assert.match(pendingWarning(s.database, "x") ?? "", /8 of 10 undelivered/);
  s.close();
});

test("the bridge's own notices are never refused by the cap", () => {
  const s = capped();
  fill(s, CAP);
  const notice = s.send({ fromAgent: "bridge", toAgent: "x", body: "automated notice" });
  assert.ok(notice.id > 0);
  s.close();
});
