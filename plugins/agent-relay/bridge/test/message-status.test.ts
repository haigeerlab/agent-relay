// agent-relay ops-commands (D45): the status of one message, and a wait on its outcome.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { transition } from "../src/delivery.js";
import { session } from "./support/session.js";

function fresh(): BridgeStore {
  const s = new BridgeStore(":memory:");
  for (const name of ["s", "x"]) s.register(name);
  return s;
}

test("a message's status names its outcome: pending, acknowledged, replied, failed or expired", () => {
  const s = fresh();
  const m = s.send({ fromAgent: "s", toAgent: "x", body: "do it", threadId: "t" });
  const pending = s.messageStatus(m.id);
  assert.equal(pending?.outcome, "pending");
  assert.equal(pending?.deliveryState, "queued");
  assert.equal(pending?.message.preview, "do it");
  assert.equal(pending?.acknowledgedAt, null);
  s.ack("x", [m.id]);
  assert.equal(s.messageStatus(m.id)?.outcome, "acknowledged");
  const reply = s.send({ fromAgent: "x", toAgent: "s", body: "done", replyTo: m.id });
  const replied = s.messageStatus(m.id);
  assert.equal(replied?.outcome, "replied");
  assert.deepEqual(replied?.replies, [reply.id]);

  const failed = s.send({ fromAgent: "s", toAgent: "x", body: "f" });
  transition(s.database, failed.id, "sending");
  transition(s.database, failed.id, "failed");
  assert.equal(s.messageStatus(failed.id)?.outcome, "failed");
  const expired = s.send({ fromAgent: "s", toAgent: "x", body: "e" });
  s.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1, expired.id);
  assert.equal(s.messageStatus(expired.id)?.outcome, "expired");
  const unknown = s.send({ fromAgent: "s", toAgent: "x", body: "u" });
  transition(s.database, unknown.id, "sending");
  transition(s.database, unknown.id, "unknown");
  assert.equal(s.messageStatus(unknown.id)?.outcome, "pending", "unknown may still resolve");
  assert.equal(s.messageStatus(9999), undefined);
  s.close();
});

test("bridge_wake_status and bridge_wait answer by message id for its sender or recipient only", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-status-"));
  const a = await session(dir, "claude-session-a");
  const b = await session(dir, "claude-session-b");
  const c = await session(dir, "claude-session-c");
  try {
    await a.call("bridge_register", { agent: "alice" });
    await b.call("bridge_register", { agent: "bob" });
    await c.call("bridge_register", { agent: "carol" });
    const id = (await a.call("bridge_send", { from: "alice", to: "bob", body: "please" })).json().id;

    const status = (await a.call("bridge_wake_status", { messageId: id })).json();
    assert.equal(status.outcome, "pending");
    assert.ok((await b.call("bridge_wake_status", { messageId: id })).ok, "the recipient may ask");
    const stranger = await c.call("bridge_wake_status", { messageId: id });
    assert.equal(stranger.ok, false);
    assert.match(stranger.text, /only by its sender or recipient/);
    assert.match((await a.call("bridge_wake_status", { messageId: 9999 })).text, /No message #9999/);

    const timedOut = (await a.call("bridge_wait", { agent: "alice", messageId: id, timeoutSeconds: 1 })).json();
    assert.equal(timedOut.timedOut, true);
    assert.equal(timedOut.outcome, "pending");
    assert.equal((await c.call("bridge_wait", { agent: "carol", messageId: id, timeoutSeconds: 1 })).ok, false);
    assert.equal((await a.call("bridge_wait", { agent: "bob", messageId: id, timeoutSeconds: 1 })).ok, false, "only as its own name");

    const waiting = a.call("bridge_wait", { agent: "alice", messageId: id, timeoutSeconds: 10 });
    await new Promise((resolve) => setTimeout(resolve, 300));
    const reply = (await b.call("bridge_send", { from: "bob", to: "alice", body: "done", replyTo: id })).json();
    const answered = (await waiting).json();
    assert.equal(answered.timedOut, false);
    assert.equal(answered.outcome, "replied");
    assert.deepEqual(answered.replies, [reply.id]);
    assert.equal((await a.call("bridge_inbox", { agent: "alice" })).json().count, 1, "waiting by id acknowledges nothing");
  } finally {
    await Promise.all([a.close(), b.close(), c.close()]);
  }
});
