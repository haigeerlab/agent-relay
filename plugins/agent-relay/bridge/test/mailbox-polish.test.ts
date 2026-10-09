// agent-relay mailbox-polish (D154, D155): a delivered message never keeps reading `unknown`.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { session } from "./support/session.js";

/** A mailbox where `bob` has one message whose wake ended `unknown`, as after an unconfirmed submission. */
function unknownMessage(dir: string): number {
  const store = new BridgeStore(join(dir, "bridge.sqlite"));
  store.register("alice");
  store.register("bob");
  const message = store.send({ fromAgent: "alice", toAgent: "bob", body: "work while you were away", wake: false });
  store.database.prepare("UPDATE messages SET delivery_state = 'unknown' WHERE id = ?").run(message.id);
  store.close();
  return message.id;
}

test("the inbox call that fetches an unknown message already shows it accepted (D154)", async () => {
  for (const how of ["list", "part", "wait"] as const) {
    const dir = mkdtempSync(join(tmpdir(), "agent-relay-polish-read-"));
    const id = unknownMessage(dir);
    const bob = await session(dir, "claude-bob");
    try {
      assert.ok((await bob.call("bridge_register", { agent: "bob" })).ok);
      const result = how === "list" ? (await bob.call("bridge_inbox", { agent: "bob" })).json().messages[0]
        : how === "part" ? (await bob.call("bridge_inbox", { agent: "bob", messageId: id })).json().message
          : (await bob.call("bridge_wait", { agent: "bob", timeoutSeconds: 1, acknowledge: false })).json().messages[0];
      assert.equal(result.id, id, how);
      assert.equal(result.deliveryState, "accepted", how);
    } finally {
      await bob.close();
    }
  }
});

test("the recipient's reply is evidence that the original arrived (D155)", () => {
  const store = new BridgeStore(join(mkdtempSync(join(tmpdir(), "agent-relay-polish-reply-")), "bridge.sqlite"));
  for (const name of ["alice", "bob", "carol"]) store.register(name);
  store.wakes.bind("bob", { app: "claude", sessionId: "claude-bob" });
  const unknown = (body: string) => {
    const message = store.send({ fromAgent: "alice", toAgent: "bob", body });
    store.database.prepare("UPDATE messages SET delivery_state = 'unknown' WHERE id = ?").run(message.id);
    store.database.prepare("UPDATE wake_jobs SET state = 'unknown' WHERE message_id = ?").run(message.id);
    return message.id;
  };
  const state = (id: number) => store.messageById(id)?.deliveryState;

  const first = unknown("first");
  store.send({ fromAgent: "bob", toAgent: "alice", body: "done", replyTo: first });
  assert.equal(state(first), "accepted");
  assert.equal(store.wakes.forMessage(first)?.state, "read");

  const second = unknown("second");
  assert.throws(() => store.send({ fromAgent: "carol", toAgent: "alice", body: "not mine", replyTo: second }));
  store.send({ fromAgent: "bob", toAgent: "alice", body: "unrelated" });
  assert.equal(state(second), "unknown", "only the recipient's reply to that message counts");

  const broadcast = store.send({ fromAgent: "alice", toAgent: "*", body: "all" });
  store.send({ fromAgent: "bob", toAgent: "alice", body: "seen", replyTo: broadcast.id });
  assert.equal(state(broadcast.id), null, "a broadcast has no delivery state");
  store.close();
});
