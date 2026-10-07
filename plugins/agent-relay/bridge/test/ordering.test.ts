// agent-relay durable-ordering: one ping in flight per recipient, oldest first; recipients never block each other;
// a message the recipient already fetched is not pinged again.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";

function store(path = ":memory:"): BridgeStore {
  const s = new BridgeStore(path);
  for (const name of ["s", "x", "y"]) s.register(name);
  s.wakes.bind("x", { app: "codex", sessionId: "thread-x" });
  s.wakes.bind("y", { app: "codex", sessionId: "thread-y" });
  return s;
}

test("a recipient's second message waits while its first is backing off", () => {
  const s = store();
  const first = s.send({ fromAgent: "s", toAgent: "x", body: "first" });
  const second = s.send({ fromAgent: "s", toAgent: "x", body: "second" });
  const now = Date.now() + 1;
  const job = s.wakes.claim(now);
  assert.equal(job?.messageId, first.id);
  s.wakes.finish(job!, { state: "pending", detail: "offline" });
  assert.equal(s.wakes.claim(now + 500), null, "the second must not overtake the backing-off first");
  assert.equal(s.wakes.forMessage(second.id)?.state, "pending");
  assert.equal(s.wakes.claim(now + 120_000)?.messageId, first.id);
  s.close();
});

test("a recipient whose ping keeps failing does not delay another recipient", () => {
  const s = store();
  const toX = s.send({ fromAgent: "s", toAgent: "x", body: "x" });
  const toY = s.send({ fromAgent: "s", toAgent: "y", body: "y" });
  const now = Date.now() + 1;
  const job = s.wakes.claim(now);
  assert.equal(job?.messageId, toX.id);
  s.wakes.finish(job!, { state: "pending", detail: "offline" });
  assert.equal(s.wakes.claim(now + 1)?.messageId, toY.id);
  s.close();
});

test("two bridge processes never have two pings to one recipient in flight", () => {
  const path = join(mkdtempSync(join(tmpdir(), "bridge-order-")), "bridge.sqlite");
  const a = store(path);
  const b = new BridgeStore(path);
  a.send({ fromAgent: "s", toAgent: "x", body: "first" });
  a.send({ fromAgent: "s", toAgent: "x", body: "second" });
  const now = Date.now() + 1;
  assert.ok(a.wakes.claim(now));
  assert.equal(b.wakes.claim(now), null);
  a.close(); b.close();
});

test("a head stuck in unknown does not hold the recipient's queue", () => {
  const s = store();
  s.send({ fromAgent: "s", toAgent: "x", body: "first" });
  const second = s.send({ fromAgent: "s", toAgent: "x", body: "second" });
  const now = Date.now() + 1;
  assert.ok(s.wakes.claim(now));
  assert.equal(s.wakes.claim(now + 31_000)?.messageId, second.id);
  s.close();
});

test("a message the recipient already fetched is not pinged, and stays visible to its sender", () => {
  const s = store();
  const message = s.send({ fromAgent: "s", toAgent: "x", body: "already read" });
  s.wakes.recordRead("x", [message.id]);
  assert.equal(s.wakes.claim(Date.now() + 1), null);
  const job = s.wakes.forMessage(message.id);
  assert.equal(job?.state, "read");
  assert.equal(job?.attempts, 0);
  const [entry] = s.outbox("s").entries;
  assert.deepEqual([entry?.deliveryState, entry?.wake?.state, entry?.acknowledgedAt], ["accepted", "read", null]);
  s.close();
});
