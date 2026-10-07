// agent-relay delivery-state-machine: wake outcomes and recipient fetches drive the message state.
import assert from "node:assert/strict";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { deliveryState, transition } from "../src/delivery.js";

function bound(): BridgeStore {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("b");
  s.wakes.bind("b", { app: "codex", sessionId: "thread-b" });
  return s;
}

test("each wake outcome moves the message to the matching delivery state", () => {
  const cases: Array<[string, string]> = [
    ["accepted", "accepted"], ["refused", "failed"], ["unknown", "unknown"],
    ["pending", "queued"], ["held", "queued"],
  ];
  for (const [outcome, expected] of cases) {
    const s = bound();
    const message = s.send({ fromAgent: "a", toAgent: "b", body: outcome });
    const job = s.wakes.claim(Date.now() + 1);
    assert.ok(job, outcome);
    assert.equal(deliveryState(s.database, message.id), "sending", outcome);
    s.wakes.finish(job, { state: outcome as never, detail: outcome });
    assert.equal(deliveryState(s.database, message.id), expected, outcome);
    s.close();
  }
});

test("a lapsed submission becomes unknown and is never claimed again", () => {
  const s = bound();
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "lapsed" });
  const now = Date.now() + 1;
  assert.ok(s.wakes.claim(now));
  assert.equal(s.wakes.claim(now + 31_000), null);
  assert.equal(deliveryState(s.database, message.id), "unknown");
  assert.equal(s.wakes.forMessage(message.id)?.state, "unknown");
  assert.equal(s.wakes.claim(now + 120_000), null);
  s.close();
});

test("evidence resolves unknown to accepted: a late receipt, or the recipient fetching it", () => {
  const s = bound();
  const late = s.send({ fromAgent: "a", toAgent: "b", body: "late receipt" });
  const job = s.wakes.claim(Date.now() + 1);
  assert.ok(job);
  s.wakes.finish(job, { state: "unknown", detail: "no receipt" });
  s.wakes.finish(job, { state: "accepted", detail: "late receipt" });
  assert.equal(deliveryState(s.database, late.id), "accepted");

  const fetched = s.send({ fromAgent: "a", toAgent: "b", body: "fetched" });
  const second = s.wakes.claim(Date.now() + 2);
  assert.ok(second);
  s.wakes.finish(second, { state: "unknown", detail: "no receipt" });
  s.wakes.recordRead("b", [fetched.id]);
  assert.equal(deliveryState(s.database, fetched.id), "accepted");
  s.close();
});

test("an unbound recipient's fetch accepts the message and records when it was read", () => {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("c");
  const message = s.send({ fromAgent: "a", toAgent: "c", body: "unbound" });
  assert.equal(s.wakes.forMessage(message.id), null);
  s.wakes.recordRead("c", [message.id]);
  assert.equal(deliveryState(s.database, message.id), "accepted");
  const row = s.database.prepare("SELECT read_at FROM messages WHERE id = ?").get(message.id) as { read_at: number };
  assert.ok(Number(row.read_at) > 0);
  s.close();
});

test("fetching an expired message does not revive it", () => {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("c");
  const message = s.send({ fromAgent: "a", toAgent: "c", body: "too late" });
  transition(s.database, message.id, "expired");
  s.wakes.recordRead("c", [message.id]);
  assert.equal(deliveryState(s.database, message.id), "expired");
  s.close();
});
