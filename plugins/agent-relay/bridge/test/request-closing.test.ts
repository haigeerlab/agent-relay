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
  const answered = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const reply = store.send({ fromAgent: "helper", toAgent: "twin", body: "a", replyTo: answered.id });
  const count = () => store.outbox("helper", { includeAcknowledged: true }).entries.length;
  const before = count();
  const cases: Array<[number[], RegExp]> = [
    [[999_999], /#999999.*no message/i],
    [[notMine.id], new RegExp(`#${notMine.id}.*addressed to "other"`)],
    [[plain.id], new RegExp(`#${plain.id}.*not a request`)],
    [[answered.id], new RegExp(`#${answered.id}.*already answered by #${reply.id}`)],
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

test("two bridge processes cannot both close one request (D217)", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-closing-race-"));
  const path = join(dir, "bridge.sqlite");
  const one = fresh(path);
  const two = new BridgeStore(path);
  const b = one.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  one.deliver({ fromAgent: "helper", toAgent: "asker", body: "first answer", alsoAnswers: [b.id] });
  assert.throws(() => two.deliver({ fromAgent: "helper", toAgent: "other", body: "second answer", alsoAnswers: [b.id] }),
    new RegExp(`#${b.id}.*already answered by #`));
  assert.equal(two.outbox("helper", { includeAcknowledged: true }).entries.filter((e) => e.toAgent === "other").length, 0);
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

test("only the sender withdraws, only to the request's recipient, only while open; nothing stored on refusal (D219)", () => {
  const store = fresh();
  const theirs = store.send({ fromAgent: "twin", toAgent: "helper", body: "q", expectsReply: true });
  const toOther = store.send({ fromAgent: "asker", toAgent: "other", body: "q", expectsReply: true });
  const answered = store.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  const reply = store.send({ fromAgent: "helper", toAgent: "asker", body: "a", replyTo: answered.id });
  const sent = () => store.outbox("asker", { includeAcknowledged: true }).entries.length;
  const before = sent();
  const cases: Array<[number, RegExp]> = [
    [theirs.id, new RegExp(`#${theirs.id}.*sent by "twin"`)],
    [toOther.id, new RegExp(`#${toOther.id}.*addressed to "other"`)],
    [answered.id, new RegExp(`#${answered.id}.*already answered by #${reply.id}`)],
  ];
  for (const [id, pattern] of cases) {
    assert.throws(() => store.deliver({ fromAgent: "asker", toAgent: "helper", body: "withdraw", withdraws: [id] }), pattern);
  }
  assert.equal(sent(), before);
  store.close();
});

test("withdraw and ask anew in one message; a withdrawn request cannot be answered through alsoAnswers (D219)", () => {
  const store = fresh();
  const old = store.send({ fromAgent: "asker", toAgent: "helper", body: "review v1", expectsReply: true });
  const { message: fresh2, closed } = store.deliver({ fromAgent: "asker", toAgent: "helper", body: "review v2 instead",
    withdraws: [old.id], expectsReply: true });
  assert.deepEqual(closed, [{ id: old.id, kind: "withdrawn" }]);
  assert.deepEqual(store.owesReplies().get("helper")?.ids, [fresh2.id]);
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "a", replyTo: fresh2.id,
    alsoAnswers: [old.id] }), new RegExp(`#${old.id}.*withdrawn by #${fresh2.id}`));
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
  assert.throws(() => two.deliver({ fromAgent: "helper", toAgent: "asker", body: "late answer", alsoAnswers: [r.id] }),
    new RegExp(`#${r.id}.*withdrawn by #${first.message.id}`));
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

test("a request past its queue timeout cannot be closed even before the sweep ran (review of #130)", () => {
  const store = fresh();
  const r = store.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true, expiresInSeconds: 60 });
  const raw = (store as unknown as { db: DatabaseSync }).db;
  raw.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1000, r.id);
  assert.throws(() => store.deliver({ fromAgent: "helper", toAgent: "asker", body: "late", alsoAnswers: [r.id] }),
    new RegExp(`#${r.id}.*expired before delivery`));
  store.close();
});
