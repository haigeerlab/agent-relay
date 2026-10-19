// agent-relay codex-approval-presence D234, D235: the IPC client can send a follow broadcast and receive the one
// follower change it asked for; every other broadcast is still dropped.
import assert from "node:assert/strict";
import test from "node:test";

import { CodexIpc, IpcError } from "../src/local-ipc.js";
import { fakeCodexApp, snapshot } from "./support/fake-codex-app.js";

const unix = { skip: process.platform === "win32" };

test("a follow broadcast is sent as a broadcast frame and the followed thread's change is received", unix, async () => {
  const app = await fakeCodexApp({ onFollow: (id) => [
    { conversationId: "other-thread", hostId: "local", change: { type: "snapshot", revision: 9, conversationState: {} } },
    snapshot(id, { requests: [] }),
  ] });
  const ipc = new CodexIpc();
  try {
    await ipc.connect(app.path);
    const change = ipc.nextChange("thread-1", 1000);
    ipc.broadcast("thread-stream-following-changed", { conversationId: "thread-1", hostId: "local", following: true },
      ["owner"]);
    const got = await change;
    assert.equal(got.type, "snapshot");
    assert.deepEqual(got.conversationState, { requests: [] }, "the other thread's snapshot was not taken");
    const sent = app.received.find((f) => f.type === "broadcast");
    assert.deepEqual({ ...sent, sourceClientId: undefined }, { type: "broadcast", method: "thread-stream-following-changed",
      sourceClientId: undefined, version: 1, targetClientIds: ["owner"],
      params: { conversationId: "thread-1", hostId: "local", following: true } });
    assert.equal(sent!.sourceClientId, "test-client");
  } finally {
    ipc.close();
    await app.close();
  }
});

test("waiting for a change times out, and an oversized frame fails the waiter but keeps the connection", unix, async () => {
  const quiet = await fakeCodexApp();
  const ipc = new CodexIpc();
  try {
    await ipc.connect(quiet.path);
    await assert.rejects(ipc.nextChange("thread-1", 50), (e: unknown) => e instanceof IpcError && e.timedOut);
  } finally {
    ipc.close();
    await quiet.close();
  }
  const header = Buffer.alloc(4); header.writeUInt32LE(9 * 1024 * 1024);
  const big = await fakeCodexApp({ onFollow: () => [{ raw: header }] });
  const second = new CodexIpc();
  try {
    await second.connect(big.path);
    const change = second.nextChange("thread-1", 1000);
    second.broadcast("thread-stream-following-changed", { conversationId: "thread-1", hostId: "local", following: true },
      ["owner"]);
    await assert.rejects(change, (e: unknown) => e instanceof IpcError && !e.timedOut);
    // codex-approval-presence rework (#8194): the connection stays, so the unfollow still reaches the app.
    second.broadcast("thread-stream-following-changed", { conversationId: "thread-1", hostId: "local", following: false },
      ["owner"]);
    for (let i = 0; i < 50 && !big.received.some((f) => f.params?.following === false); i++) {
      await new Promise((ok) => setTimeout(ok, 10));
    }
    assert.ok(big.received.some((f) => f.params?.following === false), "the unfollow was sent after the oversized frame");
  } finally {
    second.close();
    await big.close();
  }
});
