// agent-relay ack-wake-atomic D130: an acknowledgement and its wake closure commit together, for every id or none.
import assert from "node:assert/strict";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";

function bound(): BridgeStore {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("b");
  s.wakes.bind("b", { app: "codex", sessionId: "thread-b" });
  return s;
}

function acknowledged(s: BridgeStore, id: number): boolean {
  return s.database.prepare("SELECT 1 FROM acknowledgements WHERE message_id = ? AND agent = 'b'").get(id) !== undefined;
}

test("a failure while closing the second wake job leaves neither message acknowledged", () => {
  const s = bound();
  const first = s.send({ fromAgent: "a", toAgent: "b", body: "one" });
  const second = s.send({ fromAgent: "a", toAgent: "b", body: "two" });
  const before = [s.wakes.forMessage(first.id)?.state, s.wakes.forMessage(second.id)?.state];
  assert.deepEqual(before, ["pending", "pending"]);

  const real = s.wakes.acknowledge.bind(s.wakes);
  let calls = 0;
  s.wakes.acknowledge = (agent: string, id: number) => {
    calls += 1;
    if (calls === 2) throw new Error("injected wake closure failure");
    real(agent, id);
  };
  assert.throws(() => s.ack("b", [first.id, second.id]), /injected wake closure failure/);

  assert.equal(acknowledged(s, first.id), false, "the first acknowledgement was rolled back");
  assert.equal(acknowledged(s, second.id), false, "the second acknowledgement was rolled back");
  assert.deepEqual([s.wakes.forMessage(first.id)?.state, s.wakes.forMessage(second.id)?.state], before,
    "both wake jobs keep their state");
  assert.equal(s.database.isTransaction, false, "no transaction is left open");
  s.close();
});

test("without a fault both are acknowledged and both wake jobs close; a repeat acknowledges nothing", () => {
  const s = bound();
  const first = s.send({ fromAgent: "a", toAgent: "b", body: "one" });
  const second = s.send({ fromAgent: "a", toAgent: "b", body: "two" });
  assert.equal(s.ack("b", [first.id, second.id]), 2);
  assert.ok(acknowledged(s, first.id) && acknowledged(s, second.id));
  assert.deepEqual([s.wakes.forMessage(first.id)?.state, s.wakes.forMessage(second.id)?.state],
    ["acknowledged", "acknowledged"]);
  assert.equal(s.ack("b", [first.id, second.id]), 0);
  s.close();
});
