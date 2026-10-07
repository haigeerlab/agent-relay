// agent-relay durable-ordering (D32): a failure between the writes of one step leaves no half-done state.
// Failures are injected with SQLite triggers that abort the step's second write, and checked from a second
// connection on the same file, as another bridge process would see it.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { deliveryState } from "../src/delivery.js";

function pair(): { a: BridgeStore; b: BridgeStore } {
  const path = join(mkdtempSync(join(tmpdir(), "bridge-durable-")), "bridge.sqlite");
  const a = new BridgeStore(path);
  a.register("s");
  a.register("r");
  a.wakes.bind("r", { app: "codex", sessionId: "thread-r" });
  return { a, b: new BridgeStore(path) };
}

function crashOn(store: BridgeStore, table: string, column: string, value: string): void {
  store.database.exec(`CREATE TRIGGER crash_${value} BEFORE UPDATE OF ${column} ON ${table}
    WHEN NEW.${column} = '${value}' BEGIN SELECT RAISE(ABORT, 'injected crash'); END`);
}

function heal(store: BridgeStore, value: string): void {
  store.database.exec(`DROP TRIGGER crash_${value}`);
}

test("a send that fails before COMMIT leaves neither the message nor its ping", () => {
  const { a, b } = pair();
  a.database.exec(`CREATE TRIGGER crash_enqueue BEFORE INSERT ON wake_jobs BEGIN SELECT RAISE(ABORT, 'injected crash'); END`);
  assert.throws(() => a.send({ fromAgent: "s", toAgent: "r", body: "lost" }), /injected crash/);
  assert.equal(b.inbox("r").length, 0);
  assert.equal(b.wakes.claim(Date.now() + 1), null);
  a.close(); b.close();
});

test("a claim that fails between taking the ping and moving the message takes nothing", () => {
  const { a, b } = pair();
  const message = a.send({ fromAgent: "s", toAgent: "r", body: "claim me" });
  crashOn(a, "messages", "delivery_state", "sending");
  assert.throws(() => a.wakes.claim(Date.now() + 1), /injected crash/);
  assert.equal(b.wakes.forMessage(message.id)?.state, "pending");
  assert.equal(deliveryState(b.database, message.id), "queued");
  heal(a, "sending");
  const job = b.wakes.claim(Date.now() + 1);
  assert.equal(job?.messageId, message.id);
  assert.equal(job?.attempts, 1);
  assert.equal(deliveryState(b.database, message.id), "sending");
  a.close(); b.close();
});

test("a finish that fails part-way records neither outcome; the lapsed ping then reads unknown on both", () => {
  const { a, b } = pair();
  const message = a.send({ fromAgent: "s", toAgent: "r", body: "finish me" });
  const job = a.wakes.claim(Date.now() + 1);
  assert.ok(job);
  crashOn(a, "messages", "delivery_state", "accepted");
  assert.throws(() => a.wakes.finish(job, { state: "accepted", detail: "turn started" }), /injected crash/);
  assert.equal(b.wakes.forMessage(message.id)?.state, "sending");
  assert.equal(deliveryState(b.database, message.id), "sending");
  heal(a, "accepted");
  assert.equal(b.wakes.claim(Date.now() + 31_000), null);
  assert.equal(b.wakes.forMessage(message.id)?.state, "unknown");
  assert.equal(deliveryState(b.database, message.id), "unknown");
  a.close(); b.close();
});

test("an expiry that fails part-way expires nothing, so no ping is ever sent for an expired message", () => {
  const { a, b } = pair();
  const message = a.send({ fromAgent: "s", toAgent: "r", body: "expire me" });
  a.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1, message.id);
  crashOn(a, "wake_jobs", "state", "expired");
  assert.throws(() => a.inbox("r"), /injected crash/);
  assert.equal(deliveryState(b.database, message.id), "queued");
  assert.equal(b.wakes.forMessage(message.id)?.state, "pending");
  heal(a, "expired");
  assert.equal(b.wakes.claim(Date.now() + 1), null);
  assert.equal(deliveryState(b.database, message.id), "expired");
  assert.equal(b.wakes.forMessage(message.id)?.state, "expired");
  a.close(); b.close();
});

test("a bridge that dies after submitting but before finishing leaves unknown on both, never resent", () => {
  const { a, b } = pair();
  const message = a.send({ fromAgent: "s", toAgent: "r", body: "submitted" });
  assert.ok(a.wakes.claim(Date.now() + 1));
  a.close();
  assert.equal(b.wakes.claim(Date.now() + 31_000), null);
  assert.equal(b.wakes.forMessage(message.id)?.state, "unknown");
  assert.equal(deliveryState(b.database, message.id), "unknown");
  assert.equal(b.wakes.claim(Date.now() + 600_000), null);
  assert.equal(b.wakes.forMessage(message.id)?.attempts, 1);
  b.close();
});
