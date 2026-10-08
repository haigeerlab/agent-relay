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

// D100's note covers this: a Codex caller has no verified host, so only a name registered through this bridge
// process is its own; a Claude caller's verified session survives a bridge restart.
test("after a bridge restart a Codex identity must register again before its reads count; a Claude one need not", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-read-receipt-restart-"));
  const first = await session(dir, null);
  const claudeFirst = await session(dir, "claude-kept");
  assert.ok((await first.call("bridge_register", { agent: "cx" })).ok);
  assert.ok((await claudeFirst.call("bridge_register", { agent: "cl" })).ok);
  await Promise.all([first.close(), claudeFirst.close()]);

  const codex = await session(dir, null);
  const claude = await session(dir, "claude-kept");
  try {
    const before = (await codex.call("bridge_inbox", { agent: "cx" })).json();
    assert.equal(before.readRecorded, false);
    assert.match(before.readNote, /call bridge_register with it from this session again/);
    assert.ok((await codex.call("bridge_register", { agent: "cx" })).ok);
    assert.equal((await codex.call("bridge_inbox", { agent: "cx" })).json().readRecorded, true);

    assert.equal((await claude.call("bridge_inbox", { agent: "cl" })).json().readRecorded, true,
      "the verified Claude session is recognised without registering again");
  } finally {
    await Promise.all([codex.close(), claude.close()]);
  }
});

// D102: whatever reads happen, a message is pinged successfully at most once, and a job never goes back to pending.
test("no read pattern makes a message pinged more than once", () => {
  const s = new BridgeStore(":memory:");
  s.register("sender");
  s.register("cx");
  s.wakes.bind("cx", { app: "codex", sessionId: "thread-cx" });
  const accepted = new Map<number, number>();
  let offline = true;
  // The dispatcher's loop with a fake transport: offline at first (pending, retried), then reachable.
  const tick = (now: number) => {
    const job = s.wakes.claim(now);
    if (!job) return;
    const state = offline ? "pending" : "accepted";
    if (state === "accepted") accepted.set(job.messageId, (accepted.get(job.messageId) ?? 0) + 1);
    s.wakes.finish(job, { state, detail: state, reason: "offline" });
  };
  const ids = ["bystander read first", "owner read first", "unrecorded own read", "read again and again"]
    .map((body) => s.send({ fromAgent: "sender", toAgent: "cx", body }).id);
  let now = Date.now() + 1;
  for (let step = 0; step < 4; step += 1) tick((now += 70_000)); // a few offline retries
  // A bystander's or an unregistered Codex session's read records nothing (D99): no recordRead call at all.
  s.wakes.recordRead("cx", [ids[1]!]); // the owner's own read before its ping
  offline = false;
  for (let step = 0; step < 20; step += 1) {
    tick((now += 70_000));
    if (step % 3 === 0) s.wakes.recordRead("cx", [ids[3]!]); // the owner reads again and again
  }
  assert.equal(accepted.get(ids[1]!) ?? 0, 0, "a message its owner already read is not pinged");
  for (const id of ids) assert.ok((accepted.get(id) ?? 0) <= 1, `message #${id} pinged at most once`);
  // Reads that record nothing leave the ping to happen, once: the recipient is still told.
  for (const id of [ids[0]!, ids[2]!]) assert.equal(accepted.get(id), 1, `message #${id} pinged once`);
  for (const id of ids) {
    const state = s.wakes.forMessage(id)?.state;
    assert.ok(state !== "pending" && state !== "sending", `message #${id} job ended as ${state}`);
  }
  s.close();
});
