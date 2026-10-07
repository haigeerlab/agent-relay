// agent-relay delivery-state-machine: a message nobody fetched in time expires and is never delivered (D27).
import assert from "node:assert/strict";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { deliveryState, transition } from "../src/delivery.js";

function lapse(s: BridgeStore, id: number): void {
  s.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1, id);
}

test("an unfetched message past its timeout expires, leaves the inbox and the unread count", () => {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("c");
  const stale = s.send({ fromAgent: "a", toAgent: "c", body: "stale request" });
  const fresh = s.send({ fromAgent: "a", toAgent: "c", body: "fresh request" });
  lapse(s, stale.id);
  assert.deepEqual(s.inbox("c").map((m) => m.id), [fresh.id]);
  assert.equal(s.countUnread("c"), 1);
  assert.equal(deliveryState(s.database, stale.id), "expired");
  const all = s.inbox("c", { includeExpired: true });
  assert.deepEqual(all.map((m) => [m.id, m.deliveryState]), [[stale.id, "expired"], [fresh.id, "queued"]]);
  s.close();
});

test("an expired message is never pinged: its wake job is cancelled and never claimed", () => {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("b");
  s.wakes.bind("b", { app: "codex", sessionId: "thread-b" });
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "never deliver late" });
  lapse(s, message.id);
  assert.equal(s.wakes.claim(Date.now() + 1), null);
  assert.equal(deliveryState(s.database, message.id), "expired");
  const job = s.wakes.forMessage(message.id);
  assert.equal(job?.state, "expired");
  assert.match(job?.detail ?? "", /Message expired before delivery/);
  // The sender is told, through the usual failure notice.
  assert.equal(s.wakes.claimFailure(Date.now())?.messageId, message.id);
  s.close();
});

test("only queued messages expire: accepted, sending and unknown ones keep their state", () => {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("c");
  const ids: Record<string, number> = {};
  for (const state of ["accepted", "sending", "unknown"]) {
    const id = s.send({ fromAgent: "a", toAgent: "c", body: state }).id;
    if (state === "accepted") transition(s.database, id, "accepted");
    else {
      transition(s.database, id, "sending");
      if (state === "unknown") transition(s.database, id, "unknown");
    }
    lapse(s, id);
    ids[state] = id;
  }
  assert.equal(s.inbox("c").length, 3);
  for (const [state, id] of Object.entries(ids)) assert.equal(deliveryState(s.database, id), state);
  s.close();
});
