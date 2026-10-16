// agent-relay ack-records-read D197: acknowledging a message also records that it was read, when that was not recorded
// yet. read_at then means "fetched or handled", not "the body was certainly read".
import assert from "node:assert/strict";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";

function store(): BridgeStore {
  const s = new BridgeStore(":memory:");
  for (const name of ["a", "b", "c"]) s.register(name);
  return s;
}

function readAt(s: BridgeStore, id: number): number | null {
  const row = s.database.prepare("SELECT read_at FROM messages WHERE id = ?").get(id) as { read_at: number | null };
  return row.read_at === null ? null : Number(row.read_at);
}

test("acknowledging an unread message records it as read in the same step", () => {
  const s = store();
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "work" });
  assert.equal(readAt(s, message.id), null);
  assert.equal(s.ack("b", [message.id]), 1);
  assert.ok((readAt(s, message.id) ?? 0) > 0, "read_at is set by the acknowledgement");
  const entry = s.outbox("a").entries.find((e) => e.id === message.id);
  assert.equal(entry, undefined, "acknowledged messages leave the outbox");
  s.close();
});

test("an earlier read time is kept, and nothing changes for ids this call does not acknowledge", () => {
  const s = store();
  const read = s.send({ fromAgent: "a", toAgent: "b", body: "read first" });
  s.database.prepare("UPDATE messages SET read_at = 1000 WHERE id = ?").run(read.id);
  s.ack("b", [read.id]);
  assert.equal(readAt(s, read.id), 1000, "an earlier read_at is kept");

  const other = s.send({ fromAgent: "a", toAgent: "b", body: "for b" });
  assert.equal(s.ack("c", [other.id]), 0, "c cannot acknowledge b's message");
  assert.equal(readAt(s, other.id), null, "an ack by another agent marks nothing read");

  const again = s.send({ fromAgent: "a", toAgent: "b", body: "twice" });
  s.ack("b", [again.id]);
  s.database.prepare("UPDATE messages SET read_at = 2000 WHERE id = ?").run(again.id);
  assert.equal(s.ack("b", [again.id]), 0);
  assert.equal(readAt(s, again.id), 2000, "a repeated ack changes nothing");

  const broadcast = s.send({ fromAgent: "a", toAgent: "*", body: "all" });
  s.ack("b", [broadcast.id]);
  assert.equal(readAt(s, broadcast.id), null, "a broadcast keeps no read_at");
  s.close();
});
