// agent-relay read-own-sent (D212, D213): a sender reads back its own messages by id; a refused read says why.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { session } from "./support/session.js";

test("a sender reads its own direct message and broadcast by id, in parts, and records no read (D212)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-read-own-sent-"));
  const a = await session(dir, "claude-read-own-sent");
  try {
    for (const agent of ["alice", "bob"]) await a.call("bridge_register", { agent });
    const body = "第一段，".repeat(20_000);
    const id = (await a.call("bridge_send", { from: "alice", to: "bob", body })).json().id;

    let read = "";
    let offset: number | undefined = 0;
    while (offset !== undefined) {
      const part = await a.call("bridge_inbox", { agent: "alice", messageId: id, bodyOffset: offset });
      assert.ok(part.ok, part.text.slice(0, 300));
      const message = part.json().message;
      assert.equal(message.direction, "sent");
      assert.equal(part.json().readRecorded, false);
      assert.match(part.json().readNote, /reading it back records nothing/);
      read += message.body;
      offset = message.nextOffset;
    }
    assert.equal(read, body);

    // The recipient's message stays unread: no read time, its ping not marked read, still in its unread inbox.
    const store = new BridgeStore(join(dir, "bridge.sqlite"));
    const row = store.database.prepare("SELECT read_at FROM messages WHERE id = ?").get(id) as { read_at: number | null };
    assert.equal(row.read_at, null);
    const job = store.database.prepare("SELECT state FROM wake_jobs WHERE message_id = ?").get(id) as { state: string } | undefined;
    assert.notEqual(job?.state, "read");
    store.close();
    assert.equal((await a.call("bridge_inbox", { agent: "bob" })).json().messages[0].id, id);

    const received = await a.call("bridge_inbox", { agent: "bob", messageId: id });
    assert.equal(received.json().message.direction, "received");

    const broadcast = (await a.call("bridge_send", { from: "alice", to: "*", body: "everyone" })).json().id;
    const own = await a.call("bridge_inbox", { agent: "alice", messageId: broadcast });
    assert.ok(own.ok, own.text);
    assert.equal(own.json().message.body, "everyone");
    assert.equal(own.json().message.direction, "sent");
  } finally {
    await a.close();
  }
});

test("a sender's own expired message is still history it can read by id (D212)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-read-own-expired-"));
  const a = await session(dir, "claude-read-own-expired");
  try {
    for (const agent of ["alice", "bob"]) await a.call("bridge_register", { agent });
    const id = (await a.call("bridge_send", { from: "alice", to: "bob", body: "too late" })).json().id;
    const store = new BridgeStore(join(dir, "bridge.sqlite"));
    store.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1, id);
    store.inbox("bob");
    store.close();
    const read = await a.call("bridge_inbox", { agent: "alice", messageId: id });
    assert.ok(read.ok, read.text);
    assert.equal(read.json().message.deliveryState, "expired");
  } finally {
    await a.close();
  }
});

test("a read by id of someone else's message, or of no message, says why (D213)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-read-other-"));
  const a = await session(dir, "claude-read-other");
  try {
    for (const agent of ["alice", "bob", "carol"]) await a.call("bridge_register", { agent });
    const id = (await a.call("bridge_send", { from: "alice", to: "bob", body: "private" })).json().id;
    const other = await a.call("bridge_inbox", { agent: "carol", messageId: id });
    assert.equal(other.ok, false);
    assert.match(other.text, new RegExp(`Message #${id} was not sent to "carol" and not sent by it`));
    assert.match(other.text, /by id an agent reads only messages it received or sent/);
    assert.match(other.text, /ask its sender "alice" or its recipient "bob"/);
    assert.doesNotMatch(other.text, /private/);
    assert.doesNotMatch(other.text, /agent: "bob"/, "no hint to read another agent's inbox");
    const none = await a.call("bridge_inbox", { agent: "carol", messageId: 99999 });
    assert.equal(none.ok, false);
    assert.match(none.text, /There is no message #99999/);
  } finally {
    await a.close();
  }
});
