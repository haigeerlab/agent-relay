// agent-relay inbox-read-receipt: only the identity itself records a read (D99) and the result says which (D100).
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";

import { BridgeStore } from "../src/bridge-store.js";
import { session } from "./support/session.js";

function store(dir: string): BridgeStore {
  return new BridgeStore(join(dir, "bridge.sqlite"));
}

function deliveryState(dir: string, id: number): string | null | undefined {
  const s = store(dir);
  try {
    return s.messageStatus(id)?.deliveryState;
  } finally {
    s.close();
  }
}

function lastSeen(dir: string, agent: string): string | undefined {
  const s = store(dir);
  try {
    return s.getAgent(agent)?.lastSeen;
  } finally {
    s.close();
  }
}

const NOT_RECORDED = (agent: string) =>
  `This read was not recorded: "${agent}" is not an identity of this session, so its messages stay unread for ` +
  `delivery and its recipient will still be pinged. If "${agent}" is this session's own name (for example after the ` +
  `bridge restarted), call bridge_register with it from this session again.`;

test("a bystander's bridge_inbox leaves delivery alone and says so; the owner's read records it", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-read-receipt-"));
  const owner = await session(dir, "claude-owner");
  const bystander = await session(dir, "claude-bystander");
  try {
    assert.ok((await owner.call("bridge_register", { agent: "owner" })).ok);
    assert.ok((await bystander.call("bridge_register", { agent: "bystander" })).ok);
    const sent = (await bystander.call("bridge_send", { from: "bystander", to: "owner", body: "hello", wake: false })).json();
    assert.equal(deliveryState(dir, sent.id), "queued");
    const seenBefore = lastSeen(dir, "owner");
    await sleep(20);

    const peek = (await bystander.call("bridge_inbox", { agent: "owner" })).json();
    assert.equal(peek.count, 1, "the listing itself is unchanged");
    assert.equal(peek.readRecorded, false);
    assert.equal(peek.readNote, NOT_RECORDED("owner"));
    assert.equal(deliveryState(dir, sent.id), "queued", "a bystander's read is not delivery");
    assert.equal(lastSeen(dir, "owner"), seenBefore, "a bystander's read is not the owner's activity");

    const own = (await owner.call("bridge_inbox", { agent: "owner" })).json();
    assert.equal(own.readRecorded, true);
    assert.equal(own.readNote, undefined);
    assert.equal(deliveryState(dir, sent.id), "accepted");
    assert.notEqual(lastSeen(dir, "owner"), seenBefore);

    const empty = (await owner.call("bridge_inbox", { agent: "owner", afterId: sent.id })).json();
    assert.deepEqual([empty.count, empty.readRecorded], [0, true], "an empty page still says whether it counted");
  } finally {
    await Promise.all([owner.close(), bystander.close()]);
  }
});

test("bridge_wait without acknowledging records a read only for the identity itself", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-read-receipt-wait-"));
  const owner = await session(dir, "claude-owner");
  const bystander = await session(dir, "claude-bystander");
  try {
    assert.ok((await owner.call("bridge_register", { agent: "owner" })).ok);
    assert.ok((await bystander.call("bridge_register", { agent: "bystander" })).ok);
    const sent = (await bystander.call("bridge_send", { from: "bystander", to: "owner", body: "hi", wake: false })).json();

    const peek = (await bystander.call("bridge_wait", { agent: "owner", acknowledge: false, timeoutSeconds: 1 })).json();
    assert.equal(peek.count, 1);
    assert.equal(peek.readRecorded, false);
    assert.equal(peek.readNote, NOT_RECORDED("owner"));
    assert.equal(deliveryState(dir, sent.id), "queued");

    const own = (await owner.call("bridge_wait", { agent: "owner", acknowledge: false, timeoutSeconds: 1 })).json();
    assert.equal(own.readRecorded, true);
    assert.equal(deliveryState(dir, sent.id), "accepted");

    const acked = (await owner.call("bridge_wait", { agent: "owner", timeoutSeconds: 1 })).json();
    assert.equal(acked.readRecorded, true, "acknowledging waits are always the identity's own");
  } finally {
    await Promise.all([owner.close(), bystander.close()]);
  }
});

test("a bystander's bridge_outbox is not the sender's activity", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-read-receipt-outbox-"));
  const owner = await session(dir, "claude-owner");
  const bystander = await session(dir, "claude-bystander");
  try {
    assert.ok((await owner.call("bridge_register", { agent: "owner" })).ok);
    assert.ok((await bystander.call("bridge_register", { agent: "bystander" })).ok);
    const before = lastSeen(dir, "owner");
    await sleep(20);
    assert.ok((await bystander.call("bridge_outbox", { agent: "owner" })).ok);
    assert.equal(lastSeen(dir, "owner"), before);
    assert.ok((await owner.call("bridge_outbox", { agent: "owner" })).ok);
    assert.notEqual(lastSeen(dir, "owner"), before);
  } finally {
    await Promise.all([owner.close(), bystander.close()]);
  }
});
