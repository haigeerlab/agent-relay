// agent-relay request-closing (D216–D222): one answer closes several requests; a sender withdraws its own.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { SCHEMA_VERSION } from "../src/schema.js";

function fresh(path = ":memory:"): BridgeStore {
  const s = new BridgeStore(path);
  for (const name of ["asker", "twin", "helper", "other"]) s.register(name);
  return s;
}

test("schema 7 adds request_closures; requests from before it have no closure (D216)", () => {
  assert.equal(SCHEMA_VERSION, 7);
  const dir = mkdtempSync(join(tmpdir(), "bridge-v6-v7-"));
  const path = join(dir, "bridge.sqlite");
  const first = fresh(path);
  const old = first.send({ fromAgent: "asker", toAgent: "helper", body: "written before 7", expectsReply: true });
  first.close();
  const raw = new DatabaseSync(path);
  raw.exec("DROP TABLE request_closures");
  raw.exec("PRAGMA user_version = 6");
  raw.close();

  const store = new BridgeStore(path, { backupDir: join(dir, "backups") });
  assert.deepEqual(store.migration, { from: 6, to: 7, newer: false });
  assert.deepEqual(store.owesReplies().get("helper")?.ids, [old.id]);
  store.close();
  const reopened = new BridgeStore(path, { backupDir: join(dir, "backups") });
  assert.deepEqual(reopened.migration, { from: 7, to: 7, newer: false });
  reopened.close();
});

test("a closure row closes a request in every view (D216)", () => {
  const store = fresh();
  const request = store.send({ fromAgent: "asker", toAgent: "helper", body: "please", expectsReply: true });
  assert.equal(store.owesReplies().get("helper")?.count, 1);
  const raw = (store as unknown as { db: DatabaseSync }).db;
  raw.prepare("INSERT INTO request_closures (request_id, message_id, kind, closed_at) VALUES (?, ?, 'withdrawn', ?)")
    .run(request.id, request.id, new Date().toISOString());
  assert.equal(store.owesReplies().get("helper"), undefined);
  assert.equal(store.outbox("asker", { awaitingReply: true }).entries.length, 0);
  store.close();
});

// D217: one answer closes several requests addressed to its sender.
test("alsoAnswers closes further requests with the replyTo answer, in every view (D217, D220, D222)", () => {
  const store = fresh();
  const a = store.send({ fromAgent: "asker", toAgent: "helper", body: "review X", expectsReply: true });
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "review X too", expectsReply: true });
  assert.equal(store.owesReplies().get("helper")?.count, 2);
  const { message: answer, closed } = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "X is fine",
    replyTo: a.id, alsoAnswers: [b.id] });
  assert.deepEqual(closed, [{ id: b.id, kind: "answered" }]);
  assert.equal(store.owesReplies().get("helper"), undefined);
  const entry = store.outbox("twin", { includeAcknowledged: true }).entries.find((e) => e.id === b.id);
  assert.deepEqual(entry?.closedBy, { messageId: answer.id, kind: "answered" });
  assert.deepEqual(entry?.replies, [answer.id]);
  assert.equal(store.messageStatus(b.id)?.outcome, "replied");
  assert.equal(store.outbox("twin", { awaitingReply: true }).entries.length, 0);
  assert.equal(store.outbox("asker", { includeAcknowledged: true }).entries.find((e) => e.id === a.id)?.closedBy, undefined);
  store.close();
});

test("alsoAnswers works without replyTo and is refused on a broadcast (D217)", () => {
  const store = fresh();
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const { closed } = store.deliver({ fromAgent: "helper", toAgent: "other", body: "done", alsoAnswers: [b.id] });
  assert.deepEqual(closed, [{ id: b.id, kind: "answered" }]);
  const c = store.send({ fromAgent: "twin", toAgent: "helper", body: "q2", expectsReply: true });
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "*", body: "all", alsoAnswers: [c.id] }),
    /broadcast/);
  store.close();
});

test("every alsoAnswers refusal names the id and stores nothing (D217)", () => {
  const store = fresh();
  const mine = store.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  const notMine = store.send({ fromAgent: "asker", toAgent: "other", body: "q", expectsReply: true });
  const plain = store.send({ fromAgent: "asker", toAgent: "helper", body: "fyi" });
  const count = () => store.outbox("helper", { includeAcknowledged: true }).entries.length;
  const before = count();
  const cases: Array<[number[], RegExp]> = [
    [[999_999], /#999999.*no message/i],
    [[notMine.id], new RegExp(`#${notMine.id}.*addressed to "other"`)],
    [[plain.id], new RegExp(`#${plain.id}.*not a request`)],
    [[mine.id, mine.id], /twice/],
    [Array.from({ length: 21 }, (_, i) => mine.id + i), /at most 20/],
  ];
  for (const [ids, pattern] of cases) {
    assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "x", alsoAnswers: ids }), pattern);
  }
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "x", replyTo: mine.id,
    alsoAnswers: [mine.id] }), /also the replyTo/);
  assert.equal(count(), before, "nothing was stored");
  assert.equal(store.owesReplies().get("helper")?.ids.includes(mine.id), true);
  store.close();
});

test("a retry with the same key and list is a duplicate; a different list is refused (D217)", () => {
  const store = fresh();
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const c = store.send({ fromAgent: "other", toAgent: "helper", body: "q", expectsReply: true });
  const first = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", idempotencyKey: "k",
    alsoAnswers: [b.id] });
  const again = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", idempotencyKey: "k",
    alsoAnswers: [b.id] });
  assert.equal(again.duplicate, true);
  assert.equal(again.message.id, first.message.id);
  assert.deepEqual(again.closed, [{ id: b.id, kind: "answered" }]);
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", idempotencyKey: "k",
    alsoAnswers: [b.id, c.id] }), /alsoAnswers/);
  assert.equal(store.owesReplies().get("helper")?.ids.includes(c.id), true);
  store.close();
});

test("a second store closing an already closed request, one after the other, skips it in its pre-check (D217, D237)", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-closing-race-"));
  const path = join(dir, "bridge.sqlite");
  const one = fresh(path);
  const two = new BridgeStore(path);
  const b = one.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const first = one.deliver({ fromAgent: "helper", toAgent: "asker", body: "first answer", alsoAnswers: [b.id] });
  const second = two.deliver({ fromAgent: "helper", toAgent: "other", body: "second answer", alsoAnswers: [b.id] });
  assert.deepEqual(second.closed, []);
  assert.deepEqual(second.skipped, [{ id: b.id, reason: "answered", by: first.message.id }]);
  assert.equal(two.outbox("helper", { includeAcknowledged: true }).entries.filter((e) => e.toAgent === "other").length, 1);
  one.close();
  two.close();
});

test("an answer through alsoAnswers counts as read by its recipient (D217, D155)", () => {
  const store = fresh();
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", alsoAnswers: [b.id] });
  assert.equal(store.messageStatus(b.id)?.deliveryState, "accepted");
  store.close();
});

// D218: the other requester of a twin pair hears of the answer and may read it.
test("the other requester gets one notice and can read the answer by id (D218)", () => {
  const store = fresh();
  const a = store.send({ fromAgent: "asker", toAgent: "helper", body: "review X", expectsReply: true, threadId: "t-a" });
  const b1 = store.send({ fromAgent: "twin", toAgent: "helper", body: "review X too", expectsReply: true, threadId: "t-b" });
  const b2 = store.send({ fromAgent: "twin", toAgent: "helper", body: "and Y", expectsReply: true, threadId: "t-b" });
  const { message: answer } = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "X and Y are fine",
    replyTo: a.id, alsoAnswers: [b1.id, b2.id] });
  const notices = store.inbox("twin").filter((m) => m.fromAgent === "bridge");
  assert.equal(notices.length, 1, "one notice per requester and answer");
  assert.equal(notices[0]?.threadId, "t-b");
  assert.match(notices[0]?.body ?? "", new RegExp(`#${b1.id}.*#${b2.id}`, "s"));
  assert.match(notices[0]?.body ?? "", new RegExp(`answered by #${answer.id}`));
  assert.match(notices[0]?.body ?? "", /X and Y are fine/);
  const read = store.messagePart("twin", answer.id);
  assert.equal(read?.direction, "answer");
  assert.equal(read?.body, "X and Y are fine");
  assert.equal(store.inbox("asker").some((m) => m.fromAgent === "bridge"), false, "no notice to the answered requester");
  assert.equal(store.messagePart("other", answer.id), undefined, "an unrelated agent still cannot read it");
  store.close();
});

test("no notice when the answer goes to the requester itself, or the requester is retired (D218)", () => {
  const store = fresh();
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  store.deliver({ fromAgent: "helper", toAgent: "twin", body: "a", alsoAnswers: [b.id] });
  assert.equal(store.inbox("twin").some((m) => m.fromAgent === "bridge"), false);
  const c = store.send({ fromAgent: "other", toAgent: "helper", body: "q", expectsReply: true });
  store.retire("other", { by: "test" });
  store.deliver({ fromAgent: "helper", toAgent: "asker", body: "a", alsoAnswers: [c.id] });
  assert.equal(store.inbox("other", { includeAcknowledged: true }).some((m) => m.fromAgent === "bridge"), false);
  store.close();
});

// D219: a sender withdraws its own open request, recorded as withdrawn, never as answered.
test("withdraws closes the sender's own request as withdrawn; no read, no answer (D219, D220)", () => {
  const store = fresh();
  const r = store.send({ fromAgent: "asker", toAgent: "helper", body: "review X", expectsReply: true });
  const { message: w, closed } = store.deliver({ fromAgent: "asker", toAgent: "helper", body: "no longer needed",
    withdraws: [r.id] });
  assert.deepEqual(closed, [{ id: r.id, kind: "withdrawn" }]);
  assert.equal(store.owesReplies().get("helper"), undefined);
  const status = store.messageStatus(r.id);
  assert.equal(status?.outcome, "withdrawn");
  assert.deepEqual(status?.replies, []);
  assert.equal(status?.deliveryState, "queued", "a withdrawal is not delivery evidence");
  const entry = store.outbox("asker", { includeAcknowledged: true }).entries.find((e) => e.id === r.id);
  assert.deepEqual(entry?.closedBy, { messageId: w.id, kind: "withdrawn" });
  assert.deepEqual(entry?.replies, []);
  store.close();
});

test("only the sender withdraws, only to the request's recipient; nothing stored on refusal (D219, D237)", () => {
  const store = fresh();
  const theirs = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const toOther = store.send({ fromAgent: "asker", toAgent: "other", body: "q", expectsReply: true });
  const sent = () => store.outbox("asker", { includeAcknowledged: true }).entries.length;
  const before = sent();
  const cases: Array<[number, RegExp]> = [
    [theirs.id, new RegExp(`#${theirs.id}.*sent by "twin"`)],
    [toOther.id, new RegExp(`#${toOther.id}.*addressed to "other"`)],
  ];
  for (const [id, pattern] of cases) {
    assert.throws(() => store.deliver({ fromAgent: "asker", toAgent: "helper", body: "withdraw", withdraws: [id] }), pattern);
  }
  assert.equal(sent(), before);
  store.close();
});

test("withdraw and ask anew in one message; a withdrawn request in alsoAnswers is skipped (D219, D237)", () => {
  const store = fresh();
  const old = store.send({ fromAgent: "asker", toAgent: "helper", body: "review v1", expectsReply: true });
  const { message: fresh2, closed } = store.deliver({ fromAgent: "asker", toAgent: "helper", body: "review v2 instead",
    withdraws: [old.id], expectsReply: true });
  assert.deepEqual(closed, [{ id: old.id, kind: "withdrawn" }]);
  assert.deepEqual(store.owesReplies().get("helper")?.ids, [fresh2.id]);
  const answer = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "a", replyTo: fresh2.id,
    alsoAnswers: [old.id] });
  assert.deepEqual(answer.closed, []);
  assert.deepEqual(answer.skipped, [{ id: old.id, reason: "withdrawn", by: fresh2.id }]);
  assert.deepEqual(store.outbox("asker", { includeAcknowledged: true }).entries.find((e) => e.id === old.id)?.closedBy,
    { messageId: fresh2.id, kind: "withdrawn" }, "the withdrawal stays");
  store.close();
});

test("a replyTo on a withdrawn request is allowed and wins the outcome (D220)", () => {
  const store = fresh();
  const r = store.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  const { message: w } = store.deliver({ fromAgent: "asker", toAgent: "helper", body: "withdrawn", withdraws: [r.id] });
  const reply = store.send({ fromAgent: "helper", toAgent: "asker", body: "already done", replyTo: r.id });
  const status = store.messageStatus(r.id);
  assert.equal(status?.outcome, "replied");
  assert.deepEqual(status?.replies, [reply.id]);
  const entry = store.outbox("asker", { includeAcknowledged: true }).entries.find((e) => e.id === r.id);
  assert.deepEqual(entry?.closedBy, { messageId: w.id, kind: "withdrawn" });
  store.close();
});

test("withdraws: retries, conflicts with an answer, and the list shape (D219)", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-withdraw-race-"));
  const path = join(dir, "bridge.sqlite");
  const one = fresh(path);
  const two = new BridgeStore(path);
  const r = one.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  const first = one.deliver({ fromAgent: "asker", toAgent: "helper", body: "withdrawn", idempotencyKey: "w", withdraws: [r.id] });
  const again = one.deliver({ fromAgent: "asker", toAgent: "helper", body: "withdrawn", idempotencyKey: "w", withdraws: [r.id] });
  assert.equal(again.duplicate, true);
  assert.equal(again.message.id, first.message.id);
  assert.deepEqual(again.closed, [{ id: r.id, kind: "withdrawn" }]);
  assert.throws(() => one.deliver({ fromAgent: "asker", toAgent: "helper", body: "withdrawn", idempotencyKey: "w",
    withdraws: [] }), /withdraws/);
  assert.deepEqual(two.deliver({ fromAgent: "helper", toAgent: "asker", body: "late answer", alsoAnswers: [r.id] }).skipped,
    [{ id: r.id, reason: "withdrawn", by: first.message.id }]);
  assert.throws(() => one.deliver({ fromAgent: "asker", toAgent: "*", body: "all", withdraws: [r.id] }), /broadcast/);
  one.close();
  two.close();
});

test("a failure after the closures are written rolls back the message and the closures (D216)", () => {
  const store = fresh();
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const before = store.outbox("helper", { includeAcknowledged: true }).entries.length;
  const wakes = store.wakes as unknown as { recordRead: (agent: string, ids: number[]) => void };
  const original = wakes.recordRead.bind(store.wakes);
  wakes.recordRead = () => { throw new Error("forced after the closures"); };
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "a", alsoAnswers: [b.id] }), /forced/);
  wakes.recordRead = original;
  assert.equal(store.outbox("helper", { includeAcknowledged: true }).entries.length, before);
  assert.deepEqual(store.owesReplies().get("helper")?.ids, [b.id]);
  assert.equal(store.messageStatus(b.id)?.closedBy, undefined);
  store.close();
});

test("an acknowledgement still closes nothing (D202 unchanged)", () => {
  const store = fresh();
  const r = store.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  store.ack("helper", [r.id]);
  assert.deepEqual(store.owesReplies().get("helper")?.ids, [r.id]);
  store.close();
});

// Round-2 review of #130: D35 must not swallow a new list (D217, D219).
test("the same reply resent with an alsoAnswers list is not folded into the earlier one (D35, D217)", () => {
  const store = fresh();
  const a = store.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "q too", expectsReply: true });
  const first = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", replyTo: a.id });
  const second = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", replyTo: a.id, alsoAnswers: [b.id] });
  assert.equal(second.duplicate, false);
  assert.notEqual(second.message.id, first.message.id);
  assert.deepEqual(second.closed, [{ id: b.id, kind: "answered" }]);
  assert.equal(store.owesReplies().get("helper"), undefined);
  const third = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", replyTo: a.id, alsoAnswers: [b.id] });
  assert.equal(third.duplicate, true, "the same reply with the same list still folds (D35)");
  assert.equal(third.message.id, second.message.id);
  store.close();
});

test("a request past its queue timeout is skipped as expired even before the sweep ran (review of #130, D237)", () => {
  const store = fresh();
  const r = store.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true, expiresInSeconds: 60 });
  const raw = (store as unknown as { db: DatabaseSync }).db;
  raw.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1000, r.id);
  const late = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "late", alsoAnswers: [r.id] });
  assert.deepEqual(late.skipped, [{ id: r.id, reason: "expired" }]);
  assert.deepEqual(late.closed, []);
  store.close();
});

// Revision 2026-10-19 (D237, D238): a request already closed is skipped, not refused, and the result says so.
test("an alsoAnswers request already answered by replyTo or by another alsoAnswers is skipped (D237)", () => {
  const store = fresh();
  const byReply = store.send({ fromAgent: "twin", toAgent: "helper", body: "q1", expectsReply: true });
  const reply = store.send({ fromAgent: "helper", toAgent: "twin", body: "a1", replyTo: byReply.id });
  const byAlso = store.send({ fromAgent: "other", toAgent: "helper", body: "q2", expectsReply: true });
  const earlier = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "a2", alsoAnswers: [byAlso.id] });
  const result = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "a3", alsoAnswers: [byAlso.id, byReply.id] });
  assert.equal(result.duplicate, false);
  assert.deepEqual(result.closed, []);
  assert.deepEqual(result.skipped, [{ id: byReply.id, reason: "answered", by: reply.id },
    { id: byAlso.id, reason: "answered", by: earlier.message.id }]);
  assert.equal(store.messageById(result.message.id)?.body, "a3");
  store.close();
});

test("a failed request is skipped; withdraws of an answered request is skipped (D237)", () => {
  const store = fresh();
  const failed = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const raw = (store as unknown as { db: DatabaseSync }).db;
  raw.prepare("UPDATE messages SET delivery_state = 'failed' WHERE id = ?").run(failed.id);
  assert.deepEqual(store.deliver({ fromAgent: "helper", toAgent: "asker", body: "a", alsoAnswers: [failed.id] }).skipped,
    [{ id: failed.id, reason: "failed" }]);
  const mine = store.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  const reply = store.send({ fromAgent: "helper", toAgent: "asker", body: "a", replyTo: mine.id });
  const w = store.deliver({ fromAgent: "asker", toAgent: "helper", body: "never mind", withdraws: [mine.id] });
  assert.deepEqual(w.closed, []);
  assert.deepEqual(w.skipped, [{ id: mine.id, reason: "answered", by: reply.id }]);
  assert.equal(store.outbox("asker", { includeAcknowledged: true }).entries.find((e) => e.id === mine.id)?.closedBy,
    undefined, "skipping records no closure");
  store.close();
});

test("a mix closes the open requests and skips the closed ones; no read and no notice for a skipped one (D237, D218)", () => {
  const store = fresh();
  const open = store.send({ fromAgent: "twin", toAgent: "helper", body: "open", expectsReply: true });
  const gone = store.send({ fromAgent: "other", toAgent: "helper", body: "old", expectsReply: true });
  store.deliver({ fromAgent: "other", toAgent: "helper", body: "withdrawn", withdraws: [gone.id] });
  const raw = (store as unknown as { db: DatabaseSync }).db;
  const readAt = () => (raw.prepare("SELECT read_at FROM messages WHERE id = ?").get(gone.id) as { read_at: unknown }).read_at;
  const readBefore = readAt();
  const notices = (to: string) => store.inbox(to).filter((m) => m.fromAgent === "bridge").length;
  const otherBefore = notices("other");
  const result = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "both", alsoAnswers: [gone.id, open.id] });
  assert.deepEqual(result.closed, [{ id: open.id, kind: "answered" }]);
  assert.deepEqual(result.skipped.map((s) => s.id), [gone.id]);
  assert.equal(notices("twin"), 1, "the closed request's sender is told");
  assert.equal(notices("other"), otherBefore, "the skipped request's sender is not");
  assert.equal(readAt(), readBefore, "a skipped request records no read");
  store.close();
});

test("wrong ids still refuse the whole send and store nothing, even beside a closed one (D237)", () => {
  const store = fresh();
  const gone = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  store.deliver({ fromAgent: "twin", toAgent: "helper", body: "withdrawn", withdraws: [gone.id] });
  const notMine = store.send({ fromAgent: "asker", toAgent: "other", body: "q", expectsReply: true });
  const count = () => store.outbox("helper", { includeAcknowledged: true }).entries.length;
  const before = count();
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "x", alsoAnswers: [gone.id, 999_999] }),
    /#999999.*no message/i);
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "x", alsoAnswers: [gone.id, notMine.id] }),
    new RegExp(`#${notMine.id}.*addressed to "other"`));
  assert.equal(count(), before, "nothing was stored");
  store.close();
});

test("a retry of a send that skipped a request is a duplicate, by key and by D35 (D238)", () => {
  const store = fresh();
  const old = store.send({ fromAgent: "asker", toAgent: "helper", body: "v1", expectsReply: true });
  const { message: v2 } = store.deliver({ fromAgent: "asker", toAgent: "helper", body: "v2", withdraws: [old.id],
    expectsReply: true });
  const first = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "answer", replyTo: v2.id,
    alsoAnswers: [old.id], idempotencyKey: "user-answer" });
  assert.deepEqual(first.skipped.map((s) => s.id), [old.id]);
  const byKey = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "answer", replyTo: v2.id,
    alsoAnswers: [old.id], idempotencyKey: "user-answer" });
  assert.equal(byKey.duplicate, true);
  assert.equal(byKey.message.id, first.message.id);
  // post-090-bridge D253 (revises D238): the retry lists what is closed elsewhere, as the first send did.
  assert.deepEqual(byKey.skipped, [{ id: old.id, reason: "withdrawn", by: v2.id }]);
  const byReply = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "answer", replyTo: v2.id,
    alsoAnswers: [old.id] });
  assert.equal(byReply.duplicate, true);
  assert.equal(byReply.message.id, first.message.id);
  assert.deepEqual(byReply.skipped, [{ id: old.id, reason: "withdrawn", by: v2.id }]);
  store.close();
});

test("a lenient D35 fold reports the ids closed elsewhere, for answers and withdrawals (D253)", () => {
  const store = fresh();
  const asked = store.send({ fromAgent: "asker", toAgent: "helper", body: "main", expectsReply: true });
  const open = store.send({ fromAgent: "twin", toAgent: "helper", body: "same", expectsReply: true });
  const gone = store.send({ fromAgent: "other", toAgent: "helper", body: "same", expectsReply: true });
  const rival = store.deliver({ fromAgent: "helper", toAgent: "other", body: "done", replyTo: gone.id }).message;
  const send = () => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "answer", replyTo: asked.id,
    alsoAnswers: [gone.id, open.id] });
  const first = send();
  assert.deepEqual(first.closed, [{ id: open.id, kind: "answered" }]);
  const retry = send();
  assert.equal(retry.duplicate, true);
  assert.deepEqual(retry.skipped, [{ id: gone.id, reason: "answered", by: rival.id }]);
  assert.deepEqual(retry.skipped, first.skipped);

  const mine = store.send({ fromAgent: "helper", toAgent: "asker", body: "q1", expectsReply: true });
  const mine2 = store.send({ fromAgent: "helper", toAgent: "asker", body: "q2", expectsReply: true });
  store.deliver({ fromAgent: "helper", toAgent: "asker", body: "never mind q2", withdraws: [mine2.id] });
  const reply = store.send({ fromAgent: "asker", toAgent: "helper", body: "anything else?", expectsReply: true });
  const withdraw = () => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "drop both", replyTo: reply.id,
    withdraws: [mine2.id, mine.id] });
  const firstWithdraw = withdraw();
  assert.deepEqual(firstWithdraw.closed, [{ id: mine.id, kind: "withdrawn" }]);
  const again = withdraw();
  assert.equal(again.duplicate, true);
  assert.deepEqual(again.skipped, firstWithdraw.skipped);
  assert.equal(again.skipped.length, 1);
  store.close();
});

test("an exact retry with nothing closed elsewhere still skips nothing (D253)", () => {
  const store = fresh();
  const asked = store.send({ fromAgent: "asker", toAgent: "helper", body: "main", expectsReply: true });
  const also = store.send({ fromAgent: "twin", toAgent: "helper", body: "same", expectsReply: true });
  const send = () => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "answer", replyTo: asked.id,
    alsoAnswers: [also.id], idempotencyKey: "k" });
  send();
  const retry = send();
  assert.equal(retry.duplicate, true);
  assert.deepEqual(retry.skipped, []);
  const plain = () => store.deliver({ fromAgent: "helper", toAgent: "twin", body: "plain", replyTo: also.id });
  plain();
  assert.deepEqual(plain().skipped, []);
  store.close();
});

test("losing the race between the check and the closure becomes a skip, not a refusal (D237)", () => {
  const store = fresh();
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const rival = store.send({ fromAgent: "helper", toAgent: "twin", body: "rival answer" });
  const raw = (store as unknown as { db: DatabaseSync }).db;
  const target = store as unknown as { assertClosable: (...args: unknown[]) => unknown };
  const original = target.assertClosable.bind(store);
  target.assertClosable = (...args: unknown[]) => {
    const outcome = original(...args);
    raw.prepare("INSERT INTO request_closures (request_id, message_id, kind, closed_at) VALUES (?, ?, 'answered', ?)")
      .run(b.id, rival.id, new Date().toISOString());
    return outcome;
  };
  const result = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "late", alsoAnswers: [b.id] });
  assert.deepEqual(result.closed, []);
  assert.deepEqual(result.skipped, [{ id: b.id, reason: "answered", by: rival.id }]);
  assert.equal(store.inbox("twin").filter((m) => m.fromAgent === "bridge").length, 0, "no notice for a lost race");
  // post-090-docs D256: nor a read; only requests this message closed count as read (D155).
  assert.equal((raw.prepare("SELECT read_at FROM messages WHERE id = ?").get(b.id) as { read_at: unknown }).read_at, null,
    "no read for a lost race");
  store.close();
});

test("a constraint failure without a closure row is a readable error, not a TypeError (D254)", () => {
  const store = fresh();
  const asked = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const raw = (store as unknown as { db: DatabaseSync }).db;
  raw.exec(`CREATE TRIGGER refuse_closure BEFORE INSERT ON request_closures
    BEGIN SELECT RAISE(ABORT, 'CHECK constraint failed: test'); END`);
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "a", alsoAnswers: [asked.id] }),
    (error: unknown) => !(error instanceof TypeError) && error instanceof Error
      && new RegExp(`request #${asked.id}.*message #\\d+.*CHECK constraint failed: test`).test(error.message));
  assert.equal(store.outbox("helper", { includeAcknowledged: true }).entries.length, 0, "the send stored nothing");
  store.close();
});

test("a retry naming an id a new send would refuse is refused too, even when that id was answered elsewhere (D253 review)", () => {
  const store = fresh();
  const asked = store.send({ fromAgent: "asker", toAgent: "helper", body: "main", expectsReply: true });
  const note = store.send({ fromAgent: "twin", toAgent: "helper", body: "fyi, no reply needed" });
  store.deliver({ fromAgent: "helper", toAgent: "twin", body: "thanks", replyTo: note.id });
  const notMine = store.send({ fromAgent: "asker", toAgent: "other", body: "q", expectsReply: true });
  store.deliver({ fromAgent: "other", toAgent: "asker", body: "a", replyTo: notMine.id });
  const theirs = store.send({ fromAgent: "twin", toAgent: "asker", body: "q", expectsReply: true });
  store.deliver({ fromAgent: "asker", toAgent: "twin", body: "a", replyTo: theirs.id });
  const answer = { fromAgent: "helper", toAgent: "asker", body: "answer", replyTo: asked.id };
  store.deliver({ ...answer, idempotencyKey: "k" });
  const count = () => store.outbox("helper", { includeAcknowledged: true }).entries.length;
  const before = count();
  assert.throws(() => store.deliver({ ...answer, idempotencyKey: "k", alsoAnswers: [note.id] }), /not a request/);
  assert.throws(() => store.deliver({ ...answer, alsoAnswers: [notMine.id] }), /addressed to "other"/);
  assert.throws(() => store.deliver({ ...answer, idempotencyKey: "k", withdraws: [theirs.id] }), /sent by "twin"/);
  assert.throws(() => store.deliver({ ...answer, withdraws: [999_999] }), /no message #999999/);
  assert.equal(count(), before, "nothing was stored");
  store.close();
});

test("a retry with both alsoAnswers and withdraws reports each id once, sorted, by key and by D35 (D253 review)", () => {
  const store = fresh();
  const asked = store.send({ fromAgent: "asker", toAgent: "helper", body: "main", expectsReply: true });
  const a1 = store.send({ fromAgent: "twin", toAgent: "helper", body: "same", expectsReply: true });
  const a2 = store.send({ fromAgent: "other", toAgent: "helper", body: "same", expectsReply: true });
  const w1 = store.send({ fromAgent: "helper", toAgent: "asker", body: "q1", expectsReply: true });
  const w2 = store.send({ fromAgent: "helper", toAgent: "asker", body: "q2", expectsReply: true });
  const answeredA2 = store.deliver({ fromAgent: "helper", toAgent: "other", body: "done", replyTo: a2.id }).message;
  const withdrewW2 = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "drop q2", withdraws: [w2.id] }).message;
  const send = (key?: string) => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "answer", replyTo: asked.id,
    alsoAnswers: [a2.id, a1.id], withdraws: [w2.id, w1.id], ...(key ? { idempotencyKey: key } : {}) });
  const first = send("k");
  const closed = [{ id: a1.id, kind: "answered" }, { id: w1.id, kind: "withdrawn" }];
  const skipped = [{ id: a2.id, reason: "answered", by: answeredA2.id }, { id: w2.id, reason: "withdrawn", by: withdrewW2.id }];
  assert.deepEqual(first.closed, closed);
  assert.deepEqual(first.skipped, skipped);
  for (const retry of [send("k"), send()]) {
    assert.equal(retry.duplicate, true);
    assert.equal(retry.message.id, first.message.id);
    assert.deepEqual(retry.closed, closed);
    assert.deepEqual(retry.skipped, skipped);
  }
  store.close();
});

// agent-relay delivery-robustness D264 (review of #161, M04WZ94 item 1): a key retry sweeps before it compares.
test("a key retry naming a request that expired unswept since lists it in skipped instead of refusing (D264)", () => {
  const store = fresh();
  const b = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const c = store.send({ fromAgent: "other", toAgent: "helper", body: "q", expectsReply: true, expiresInSeconds: 60 });
  const first = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", idempotencyKey: "k",
    alsoAnswers: [b.id] });
  const raw = (store as unknown as { db: DatabaseSync }).db;
  raw.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1000, c.id);
  const again = store.deliver({ fromAgent: "helper", toAgent: "asker", body: "done", idempotencyKey: "k",
    alsoAnswers: [b.id, c.id] });
  assert.equal(again.duplicate, true);
  assert.equal(again.message.id, first.message.id);
  assert.deepEqual(again.closed, [{ id: b.id, kind: "answered" }]);
  assert.deepEqual(again.skipped, [{ id: c.id, reason: "expired" }]);
  store.close();
});
