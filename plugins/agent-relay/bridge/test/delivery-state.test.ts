// agent-relay delivery-state-machine: the message delivery state and its one transition table (D28).
import assert from "node:assert/strict";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import {
  DEFAULT_QUEUE_TIMEOUT_MS, DeliveryTransitionError, deliveryState, queueTimeoutMs, transition,
} from "../src/delivery.js";

const DAY = 24 * 3_600_000;

function store(): BridgeStore {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("b");
  return s;
}

test("a direct message starts queued with a 24 h queue timeout; a broadcast has no delivery state", () => {
  assert.equal(DEFAULT_QUEUE_TIMEOUT_MS, DAY);
  const s = store();
  const before = Date.now();
  const direct = s.send({ fromAgent: "a", toAgent: "b", body: "hi", wake: false });
  assert.equal(direct.deliveryState, "queued");
  const expires = Date.parse(direct.expiresAt ?? "");
  assert.ok(expires >= before + DAY && expires <= Date.now() + DAY, direct.expiresAt ?? "none");
  const broadcast = s.send({ fromAgent: "a", toAgent: "*", body: "all", wake: false });
  assert.equal(broadcast.deliveryState, null);
  assert.equal(broadcast.expiresAt, null);
  s.close();
});

test("a send may shorten or lengthen its own queue timeout within 1 minute and 7 days", () => {
  const s = store();
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "soon", wake: false, expiresInSeconds: 120 });
  const remaining = Date.parse(message.expiresAt ?? "") - Date.now();
  assert.ok(remaining > 100_000 && remaining <= 120_000, String(remaining));
  for (const bad of [0, 59, 7 * 86_400 + 1, 1.5]) {
    assert.throws(() => s.send({ fromAgent: "a", toAgent: "b", body: "x", wake: false, expiresInSeconds: bad }),
      /expiresInSeconds/);
  }
  s.close();
});

test("BRIDGE_QUEUE_TIMEOUT_MS overrides the default only with a sane value", () => {
  assert.equal(queueTimeoutMs({}), DAY);
  assert.equal(queueTimeoutMs({ BRIDGE_QUEUE_TIMEOUT_MS: "3600000" }), 3_600_000);
  for (const bad of ["", "abc", "0", "59999", String(7 * DAY + 1)]) {
    assert.equal(queueTimeoutMs({ BRIDGE_QUEUE_TIMEOUT_MS: bad }), DAY, bad);
  }
});

test("only the allowed transitions change the state; final states never move", () => {
  const allowed: Array<[string, string]> = [
    ["queued", "sending"], ["queued", "accepted"], ["queued", "expired"],
    ["sending", "queued"], ["sending", "accepted"], ["sending", "failed"], ["sending", "unknown"],
    ["unknown", "accepted"],
  ];
  const all = ["queued", "sending", "accepted", "failed", "unknown", "expired"];
  const s = store();
  const db = s.database;
  const reach = (target: string): number => {
    const id = s.send({ fromAgent: "a", toAgent: "b", body: target, wake: false }).id;
    const path: Record<string, string[]> = {
      queued: [], sending: ["sending"], accepted: ["accepted"], failed: ["sending", "failed"],
      unknown: ["sending", "unknown"], expired: ["expired"],
    };
    for (const step of path[target] ?? []) transition(db, id, step as never);
    return id;
  };
  for (const from of all) {
    for (const to of all) {
      if (from === to) continue;
      const id = reach(from);
      const ok = allowed.some(([f, t]) => f === from && t === to);
      if (ok) {
        assert.equal(transition(db, id, to as never), true, `${from} -> ${to}`);
        assert.equal(deliveryState(db, id), to);
      } else {
        assert.throws(() => transition(db, id, to as never), DeliveryTransitionError, `${from} -> ${to}`);
        assert.equal(deliveryState(db, id), from);
      }
    }
  }
  s.close();
});

test("a row written by an older process (NULL state) reads and moves as queued", () => {
  const s = store();
  const db = s.database;
  db.prepare("INSERT INTO messages (from_agent, to_agent, body, created_at) VALUES ('a', 'b', 'old', ?)")
    .run(new Date().toISOString());
  const id = Number((db.prepare("SELECT max(id) AS id FROM messages").get() as { id: number }).id);
  assert.equal(deliveryState(db, id), "queued");
  assert.equal(transition(db, id, "sending"), true);
  assert.equal(deliveryState(db, id), "sending");
  s.close();
});

test("the sender sees each message's delivery state in the outbox and in wake status (D29)", () => {
  const s = store();
  s.wakes.bind("b", { app: "codex", sessionId: "thread-b" });
  const sent = s.send({ fromAgent: "a", toAgent: "b", body: "tracked" });
  const lapsed = s.send({ fromAgent: "a", toAgent: "b", body: "lapsed", wake: false });
  s.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1, lapsed.id);
  const job = s.wakes.claim(Date.now() + 1);
  assert.ok(job);
  s.wakes.finish(job, { state: "accepted", detail: "turn started" });
  const entries = Object.fromEntries(s.outbox("a").entries.map((entry) => [entry.id, entry]));
  assert.equal(entries[sent.id]?.deliveryState, "accepted");
  assert.equal(entries[lapsed.id]?.deliveryState, "expired");
  assert.equal(entries[sent.id]?.expiresAt, sent.expiresAt);
  assert.equal(s.wakes.forMessage(sent.id)?.deliveryState, "accepted");
  s.close();
});
