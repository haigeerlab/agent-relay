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
