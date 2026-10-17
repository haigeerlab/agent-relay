// agent-relay accepted-unread-notice D228–D230: a Codex ping the app accepted five minutes ago whose message is still
// unread and unacknowledged is a doubtful delivery (the task's mailbox connection may be closed); the user and the
// sender are told once.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { ACCEPTED_UNREAD_AFTER_MS, ACCEPTED_UNREAD_WINDOW_MS, PREVIEW_OFF_FILE } from "../src/notify.js";
import { WakeDispatcher } from "../src/wake-dispatcher.js";
import { session } from "./support/session.js";

const MIN = 60_000;

function store(path = ":memory:"): BridgeStore {
  const s = new BridgeStore(path);
  s.register("a");
  s.register("c");
  s.wakes.bind("c", { app: "codex", sessionId: "thread-c" });
  return s;
}

/** Send a→c and let its ping be accepted `ago` ms back, as the ChatGPT app confirming a new turn does. */
function accepted(s: BridgeStore, ago: number, body = "work", threadId?: string): number {
  const message = s.send({ fromAgent: "a", toAgent: "c", body, ...(threadId ? { threadId } : {}) });
  const job = s.wakes.claim()!;
  assert.equal(job.messageId, message.id);
  s.wakes.finish(job, { state: "accepted", detail: "Codex confirmed a new turn" });
  s.database.prepare("UPDATE messages SET delivery_changed_at = ? WHERE id = ?").run(Date.now() - ago, message.id);
  return message.id;
}

function doubtful(s: BridgeStore, now = Date.now()): number[] {
  return s.wakes.acceptedUnread(now).map((entry) => entry.messageId);
}

test("D228: an accepted Codex ping is doubtful once five minutes pass with the message unread", () => {
  const s = store();
  const id = accepted(s, 0);
  const acceptedAt = Number((s.database.prepare("SELECT delivery_changed_at AS t FROM messages WHERE id = ?").get(id) as { t: number }).t);
  assert.deepEqual(doubtful(s, acceptedAt + ACCEPTED_UNREAD_AFTER_MS - 1_000), [], "not at 4 min 59 s");
  const [entry] = s.wakes.acceptedUnread(acceptedAt + ACCEPTED_UNREAD_AFTER_MS);
  assert.deepEqual(entry, { messageId: id, agent: "c", fromAgent: "a", threadId: null, acceptedAt });
  assert.equal(ACCEPTED_UNREAD_AFTER_MS, 5 * MIN);
  assert.equal(ACCEPTED_UNREAD_WINDOW_MS, 24 * 60 * MIN);
});

test("D228: a read, acknowledged, old or Claude-targeted message is never doubtful", () => {
  const s = store();
  const read = accepted(s, 6 * MIN, "read");
  s.wakes.recordRead("c", [read]);
  const acked = accepted(s, 6 * MIN, "acked");
  s.ack("c", [acked]);
  accepted(s, ACCEPTED_UNREAD_WINDOW_MS + MIN, "accepted more than 24 hours ago");
  const noTime = accepted(s, 6 * MIN, "no accepted time");
  s.database.prepare("UPDATE messages SET delivery_changed_at = NULL WHERE id = ?").run(noTime);
  const doubt = accepted(s, 6 * MIN, "doubtful");
  assert.deepEqual(doubtful(s), [doubt]);

  // A job in any other state does not count, whatever the message shows.
  s.database.prepare("UPDATE wake_jobs SET state = 'unknown' WHERE message_id = ?").run(doubt);
  assert.deepEqual(doubtful(s), []);
});

test("D228 (round-2 review of #135): the job's own target decides, not the recipient's current binding", () => {
  const s = store();
  const toCodex = accepted(s, 6 * MIN, "pinged through Codex");
  s.wakes.bind("c", { app: "claude", sessionId: "claude-c" }, { replace: true });
  assert.deepEqual(doubtful(s), [toCodex], "still doubtful after the recipient was rebound to Claude");

  const toClaude = s.send({ fromAgent: "a", toAgent: "c", body: "pinged through Claude" });
  const job = s.wakes.claim()!;
  assert.equal(job.messageId, toClaude.id);
  s.wakes.finish(job, { state: "accepted", detail: "Claude took it" });
  s.database.prepare("UPDATE messages SET delivery_changed_at = ? WHERE id = ?").run(Date.now() - 6 * MIN, toClaude.id);
  s.wakes.bind("c", { app: "codex", sessionId: "thread-c2" }, { replace: true });
  assert.deepEqual(doubtful(s), [toCodex], "a Claude ping is not doubtful after the recipient was rebound to Codex");
});

/** A mailbox on disk (notice marks live next to it) with a notice log instead of real banners. */
function onDisk() {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-accepted-unread-"));
  const path = join(dir, "bridge.sqlite");
  const s = store(path);
  const log = join(dir, "notices.log");
  const lines = () => (existsSync(log) ? readFileSync(log, "utf8").trim().split("\n").filter(Boolean) : []);
  const env = { AGENT_RELAY_NOTIFY_LOG: log } as NodeJS.ProcessEnv;
  const dispatcher = (on = s) => new WakeDispatcher(on, { env, deliver: async () => ({ state: "pending", detail: "unused" }) });
  return { dir, path, s, lines, env, dispatcher };
}

function bridgeNotices(s: BridgeStore, to = "a") {
  return s.inbox(to).filter((m) => m.fromAgent === "bridge" && m.idempotencyKey?.startsWith("accepted-unread:"));
}

test("D229: one desktop notice per doubtful message, naming it and both possible causes", () => {
  const { path, s, lines, dispatcher } = onDisk();
  const fresh = accepted(s, 4 * MIN, "still within five minutes");
  const id = accepted(s, 6 * MIN, "please review the plan");
  dispatcher().checkAcceptedUnread();
  assert.equal(lines().length, 1);
  const [line] = lines();
  assert.match(line, new RegExp(`#${id}`));
  assert.match(line, /"a"/);
  assert.match(line, /c/);
  assert.match(line, /please review the plan/, "the preview follows D89");
  assert.match(line, /connection is closed/i);
  assert.match(line, /before registering/i);
  assert.doesNotMatch(line, new RegExp(`#${fresh}\\b`));

  dispatcher().checkAcceptedUnread();
  const second = new BridgeStore(path);
  dispatcher(second).checkAcceptedUnread();
  assert.equal(lines().length, 1, "a second tick and a second bridge add none");
  second.close();
});

test("D229: the notice switches silence the banner but not the sender's message", () => {
  for (const off of ["env", "file"] as const) {
    const { dir, s, lines, env } = onDisk();
    if (off === "file") writeFileSync(join(dir, "notify.off"), "");
    const id = accepted(s, 6 * MIN);
    const quiet = off === "env" ? { ...env, AGENT_RELAY_NOTIFY: "off" } : env;
    new WakeDispatcher(s, { env: quiet, deliver: async () => ({ state: "pending", detail: "unused" }) }).checkAcceptedUnread();
    assert.deepEqual(lines(), [], `no banner with notices off (${off})`);
    assert.equal(bridgeNotices(s).length, 1, `the sender is still told (${off})`);
    assert.match(bridgeNotices(s)[0].body, new RegExp(`#${id}`));
  }
});

test("D229: without previews the notice keeps the causes and drops the text", () => {
  const { dir, s, lines, dispatcher } = onDisk();
  writeFileSync(join(dir, PREVIEW_OFF_FILE), "");
  accepted(s, 6 * MIN, "secret plan text");
  dispatcher().checkAcceptedUnread();
  assert.equal(lines().length, 1);
  assert.doesNotMatch(lines()[0], /secret plan text/);
  assert.match(lines()[0], /connection is closed/i);
});

test("D230: the sender gets one bridge message per doubtful message, in its thread", () => {
  const { path, s, dispatcher } = onDisk();
  const id = accepted(s, 6 * MIN, "work", "thread-x");
  dispatcher().checkAcceptedUnread();
  const second = new BridgeStore(path);
  dispatcher(second).checkAcceptedUnread();
  dispatcher().checkAcceptedUnread();
  second.close();
  const notices = bridgeNotices(s);
  assert.equal(notices.length, 1, "two bridges and three ticks send it once");
  const [notice] = notices;
  assert.equal(notice.threadId, "thread-x");
  assert.equal(notice.idempotencyKey, `accepted-unread:${id}`);
  assert.match(notice.body, new RegExp(`#${id}`));
  assert.match(notice.body, /"c"/);
  assert.match(notice.body, /Do not reply/);
});

test("D230: no bridge message to bridge, to the recipient itself, or to an unknown or retired sender", () => {
  const { s, dispatcher } = onDisk();
  s.register("gone");
  for (const from of ["bridge", "c", "gone"]) {
    const message = s.send({ fromAgent: from, toAgent: "c", body: `from ${from}` });
    const job = s.wakes.claim();
    if (job) s.wakes.finish(job, { state: "accepted", detail: "Codex confirmed a new turn" });
    // A message to oneself has no wake job; give it one so only the sender rule can skip it.
    if (!job) {
      s.database.prepare(`INSERT INTO wake_jobs (message_id, agent, target, state, retry_at, created_at)
        VALUES (?, 'c', '{"app":"codex","sessionId":"thread-c"}', 'accepted', 0, 0)`).run(message.id);
      s.database.prepare("UPDATE messages SET delivery_state = 'accepted' WHERE id = ?").run(message.id);
    }
    s.database.prepare("UPDATE messages SET delivery_changed_at = ? WHERE id = ?").run(Date.now() - 6 * MIN, message.id);
  }
  s.retire("gone", { by: "a" });
  dispatcher().checkAcceptedUnread();
  for (const to of ["bridge", "c", "gone"]) assert.equal(bridgeNotices(s, to).length, 0, `nothing to ${to}`);
});

test("D230: bridge_outbox, bridge_wake_status and bridge_agents mark a doubtful delivery until it is read", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-accepted-unread-views-"));
  const s = store(join(dir, "bridge.sqlite"));
  const plain = s.send({ fromAgent: "a", toAgent: "c", body: "ordinary" }).id;
  s.wakes.finish(s.wakes.claim()!, { state: "accepted", detail: "Codex confirmed a new turn" });
  const id = accepted(s, 6 * MIN, "doubtful");
  const acceptedAt = Number((s.database.prepare("SELECT delivery_changed_at AS t FROM messages WHERE id = ?").get(id) as { t: number }).t);
  s.close();

  // A new bridge process, as after a ChatGPT restart: the task reads before registering its name again.
  const codex = await session(dir, null);
  try {
    const first = (await codex.call("bridge_inbox", { agent: "c" })).json();
    assert.equal(first.readRecorded, false, "a read by a name this process has not proven is not recorded");

    const outbox = (await codex.call("bridge_outbox", { agent: "a" })).json();
    const entry = outbox.entries.find((e: { id: number }) => e.id === id);
    assert.deepEqual(entry.wake.doubt, { reason: "accepted-unread", since: new Date(acceptedAt).toISOString() });
    assert.match(entry.wake.detail, /not read for five minutes/i);
    const other = outbox.entries.find((e: { id: number }) => e.id === plain);
    assert.equal(other.wake.doubt, undefined, "an ordinary accepted message carries no marker");
    assert.doesNotMatch(other.wake.detail, /not read for five minutes/i);

    const status = (await codex.call("bridge_wake_status", { messageId: id })).json();
    assert.equal(status.wake.doubt.reason, "accepted-unread");
    assert.match(status.wake.detail, /not read for five minutes/i);
    assert.equal((await codex.call("bridge_wake_status", { messageId: plain })).json().wake.doubt, undefined);

    const agents = (await codex.call("bridge_agents", {})).json();
    const c = agents.agents.find((a: { name: string }) => a.name === "c");
    assert.deepEqual(c.waiting.doubtfulIds, [id]);
    assert.deepEqual(c.waiting.ids, [plain, id], "the other waiting fields are unchanged");
    assert.equal(agents.agents.find((a: { name: string }) => a.name === "a").waiting?.doubtfulIds, undefined);

    // Registering again and reading once more, as the collab skill says, records the read and clears the marker.
    assert.ok((await codex.call("bridge_register", { agent: "c" })).ok);
    assert.equal((await codex.call("bridge_inbox", { agent: "c" })).json().readRecorded, true);
    const after = (await codex.call("bridge_outbox", { agent: "a" })).json().entries.find((e: { id: number }) => e.id === id);
    assert.equal(after.wake.doubt, undefined);
    assert.equal((await codex.call("bridge_wake_status", { messageId: id })).json().wake.doubt, undefined);
    const c2 = (await codex.call("bridge_agents", {})).json().agents.find((a: { name: string }) => a.name === "c");
    assert.equal(c2.waiting.doubtfulIds, undefined);
  } finally {
    await codex.close();
  }
});
