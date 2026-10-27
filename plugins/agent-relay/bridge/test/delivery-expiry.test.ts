// agent-relay delivery-state-machine: a message nobody fetched in time expires and is never delivered (D27).
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { DUE_FOR_EXPIRY, deliveryState, expireDue, transition } from "../src/delivery.js";

function lapse(s: BridgeStore, id: number): void {
  s.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1, id);
}

test("an unfetched message past its timeout expires, leaves the inbox and the unread count", () => {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("c");
  const stale = s.send({ fromAgent: "a", toAgent: "c", body: "stale request" });
  const fresh = s.send({ fromAgent: "a", toAgent: "c", body: "fresh request" });
  lapse(s, stale.id);
  assert.deepEqual(s.inbox("c").map((m) => m.id), [fresh.id]);
  assert.equal(s.countUnread("c"), 1);
  assert.equal(deliveryState(s.database, stale.id), "expired");
  const all = s.inbox("c", { includeExpired: true });
  assert.deepEqual(all.map((m) => [m.id, m.deliveryState]), [[stale.id, "expired"], [fresh.id, "queued"]]);
  s.close();
});

test("an expired message is never pinged: its wake job is cancelled and never claimed", () => {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("b");
  s.wakes.bind("b", { app: "codex", sessionId: "thread-b" });
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "never deliver late" });
  lapse(s, message.id);
  assert.equal(s.wakes.claim(Date.now() + 1), null);
  assert.equal(deliveryState(s.database, message.id), "expired");
  const job = s.wakes.forMessage(message.id);
  assert.equal(job?.state, "expired");
  assert.match(job?.detail ?? "", /Message expired before delivery/);
  // The sender is told, through the usual failure notice.
  assert.equal(s.wakes.claimFailure(Date.now())?.messageId, message.id);
  s.close();
});

test("only queued messages expire: accepted, sending and unknown ones keep their state", () => {
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("c");
  const ids: Record<string, number> = {};
  for (const state of ["accepted", "sending", "unknown"]) {
    const id = s.send({ fromAgent: "a", toAgent: "c", body: state }).id;
    if (state === "accepted") transition(s.database, id, "accepted");
    else {
      transition(s.database, id, "sending");
      if (state === "unknown") transition(s.database, id, "unknown");
    }
    lapse(s, id);
    ids[state] = id;
  }
  assert.equal(s.inbox("c").length, 3);
  for (const [state, id] of Object.entries(ids)) assert.equal(deliveryState(s.database, id), state);
  s.close();
});

test("the sender's notice for an expired message says it will never be delivered", async () => {
  const { deliveryFailureNotice } = await import("../src/notices.js");
  const s = new BridgeStore(":memory:");
  s.register("a");
  s.register("b");
  s.wakes.bind("b", { app: "claude", sessionId: "00000000-0000-4000-8000-000000000000" });
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "too late" });
  lapse(s, message.id);
  s.wakes.claim(Date.now() + 1);
  const job = s.wakes.claimFailure(Date.now());
  assert.ok(job);
  const notice = deliveryFailureNotice(job);
  assert.match(notice, /expired before it was delivered/);
  assert.match(notice, /will not be delivered/);
  assert.doesNotMatch(notice, /still unread/);
  assert.doesNotMatch(notice, /Bypass permissions/);
  s.close();
});

// agent-relay delivery-robustness D262: every bridge sweeps and claims every 2 s; an idle round takes no write lock.
function lockedMailbox() {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-idle-claim-"));
  const dbPath = join(dir, "bridge.sqlite");
  const s = new BridgeStore(dbPath);
  s.register("a");
  s.register("b");
  s.wakes.bind("b", { app: "codex", sessionId: "task-b" });
  const lock = () => {
    const other = new DatabaseSync(dbPath);
    other.exec("BEGIN IMMEDIATE");
    return () => { other.exec("ROLLBACK"); other.close(); };
  };
  return { s, lock };
}

test("the expiry sweep finds due messages through idx_messages_delivery, not a table scan", () => {
  const s = new BridgeStore(":memory:");
  const plan = s.database.prepare(`EXPLAIN QUERY PLAN UPDATE messages SET delivery_state = 'expired' WHERE ${DUE_FOR_EXPIRY}`)
    .all(Date.now()).map((row) => String(row.detail));
  assert.ok(plan.some((detail) => /idx_messages_delivery/.test(detail)), plan.join("; "));
  assert.ok(!plan.some((detail) => /^SCAN messages\b/.test(detail)), plan.join("; "));
  s.close();
});

test("an idle claim and an idle sweep return at once while another process holds the write lock", () => {
  const { s, lock } = lockedMailbox();
  const delivered = s.send({ fromAgent: "a", toAgent: "b", body: "done already" });
  s.wakes.finish(s.wakes.claim()!, { state: "accepted", detail: "ok" });
  assert.equal(s.wakes.forMessage(delivered.id)?.state, "accepted");
  const release = lock();
  try {
    const started = Date.now();
    assert.equal(s.wakes.claim(), null);
    assert.deepEqual(expireDue(s.database), []);
    assert.ok(Date.now() - started < 1_000, "no wait for the write lock");
  } finally {
    release();
  }
  s.close();
});

test("a claim with work to do still takes it: a due ping, a lapsed send, a due expiry", () => {
  const { s } = lockedMailbox();
  const first = s.send({ fromAgent: "a", toAgent: "b", body: "first" });
  const job = s.wakes.claim()!;
  assert.equal(job.messageId, first.id);
  // The sender stopped before finishing: after the retry time the job is recorded unknown.
  assert.equal(s.wakes.claim(Date.now() + 31_000), null);
  assert.equal(s.wakes.forMessage(first.id)?.state, "unknown");
  const second = s.send({ fromAgent: "a", toAgent: "b", body: "second" });
  lapse(s, second.id);
  assert.equal(s.wakes.claim(), null);
  assert.equal(deliveryState(s.database, second.id), "expired");
  const third = s.send({ fromAgent: "a", toAgent: "b", body: "third" });
  assert.equal(s.wakes.claim()?.messageId, third.id);
  s.close();
});

// Review of #164 (D266): the idle check matches what claimStep can take, so these idle rounds take no write lock either.
function idleWhileLocked(s: BridgeStore, dbPath: string, now: number) {
  const other = new DatabaseSync(dbPath);
  other.exec("BEGIN IMMEDIATE");
  s.database.exec("PRAGMA busy_timeout = 50");
  try {
    return s.wakes.claim(now);
  } finally {
    other.exec("ROLLBACK");
    other.close();
    s.database.exec("PRAGMA busy_timeout = 5000");
  }
}

function idleMailbox() {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-idle-claim-"));
  const dbPath = join(dir, "bridge.sqlite");
  const s = new BridgeStore(dbPath);
  s.register("a");
  s.register("b");
  s.wakes.bind("b", { app: "codex", sessionId: "task-b" });
  return { s, dbPath };
}

test("an offline recipient with two queued pings: the second, due but behind the first, takes no write lock", () => {
  const { s, dbPath } = idleMailbox();
  s.send({ fromAgent: "a", toAgent: "b", body: "one" });
  const second = s.send({ fromAgent: "a", toAgent: "b", body: "two" });
  s.wakes.finish(s.wakes.claim()!, { state: "pending", detail: "offline", reason: "offline" });
  const now = Date.now();
  assert.ok(s.wakes.forMessage(second.id)!.retryAt <= now, "the second ping is due");
  assert.equal(idleWhileLocked(s, dbPath, now), null);
  s.close();
});

test("a busy ping older than an hour but inside its day, not yet due, takes no write lock", () => {
  const { s, dbPath } = idleMailbox();
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "one" });
  s.wakes.finish(s.wakes.claim()!, { state: "pending", detail: "busy", reason: "busy" });
  const now = Date.now();
  s.database.prepare("UPDATE wake_jobs SET created_at = ?, retry_at = ?").run(now - 2 * 3_600_000, now + 50_000);
  assert.equal(idleWhileLocked(s, dbPath, now), null);
  assert.equal(s.wakes.forMessage(message.id)?.state, "pending", "still waiting, not expired");
  s.close();
});
