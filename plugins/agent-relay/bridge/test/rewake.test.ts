// agent-relay rewake-on-return D199: a recipient that comes back (registers again, or a Claude session process that
// started after its pings expired) gets its still-unhandled messages pinged once more, told when they were first sent.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import type { ClaudeSession } from "../src/claude-wake.js";
import { clockTime } from "../src/notify.js";
import { WakeDispatcher } from "../src/wake-dispatcher.js";
import { OFFLINE_WAKE_WINDOW_MS, parseProcStart, wakeNotice, type WakeJob } from "../src/wake-queue.js";
import { session } from "./support/session.js";

const HOUR = 3_600_000;

function store(path = ":memory:"): BridgeStore {
  const s = new BridgeStore(path);
  s.register("a");
  s.register("b", [], { app: "claude", sessionId: "claude-b" });
  s.wakes.bind("b", { app: "claude", sessionId: "claude-b" });
  return s;
}

/** Let `messageId`'s ping expire as it does for a stopped session: created `ago` ms back, pending offline, expired. */
function expire(s: BridgeStore, messageId: number, ago = 2 * HOUR): void {
  s.database.prepare(`UPDATE wake_jobs SET state = 'expired', pending_reason = 'offline', attempts = 63,
    created_at = ?, notified_at = ?, detail = 'Wake retry window expired; message remains unread' WHERE message_id = ?`)
    .run(Date.now() - ago, Date.now() - ago + OFFLINE_WAKE_WINDOW_MS, messageId);
}

function job(s: BridgeStore, id: number): WakeJob {
  return s.wakes.forMessage(id)!;
}

test("re-arming puts an expired, unhandled ping back in the queue and leaves everything else alone", () => {
  const s = store();
  const old = s.send({ fromAgent: "a", toAgent: "b", body: "old" });
  const acked = s.send({ fromAgent: "a", toAgent: "b", body: "acked" });
  const read = s.send({ fromAgent: "a", toAgent: "b", body: "read" });
  const timedOut = s.send({ fromAgent: "a", toAgent: "b", body: "timed out" });
  const live = s.send({ fromAgent: "a", toAgent: "b", body: "still pending" });
  for (const m of [old, acked, read, timedOut]) expire(s, m.id);
  s.database.prepare("INSERT INTO acknowledgements (message_id, agent, acked_at) VALUES (?, 'b', 'x')").run(acked.id);
  s.database.prepare("UPDATE messages SET read_at = 1 WHERE id = ?").run(read.id);
  s.database.prepare("UPDATE messages SET delivery_state = 'expired' WHERE id = ?").run(timedOut.id);
  const notifiedBefore = s.database.prepare("SELECT notified_at FROM wake_jobs WHERE message_id = ?").get(old.id);

  const before = Date.now();
  assert.equal(s.wakes.countExpired("b"), 1);
  assert.equal(s.wakes.rearm("b", { app: "claude", sessionId: "claude-b2" }, Date.now()), 1);
  const rearmed = job(s, old.id);
  assert.equal(rearmed.state, "pending");
  assert.equal(rearmed.attempts, 0);
  assert.ok(rearmed.createdAt >= before && rearmed.retryAt <= Date.now());
  assert.deepEqual(rearmed.target, { app: "claude", sessionId: "claude-b2" }, "the agent's current wake target");
  assert.match(rearmed.detail, /pinged again/i);
  assert.deepEqual(s.database.prepare("SELECT notified_at FROM wake_jobs WHERE message_id = ?").get(old.id),
    notifiedBefore, "the sender's failure notice is not sent a second time");
  for (const m of [acked, read, timedOut]) assert.equal(job(s, m.id).state, "expired", `#${m.id} stays expired`);
  assert.equal(job(s, live.id).state, "pending");
  assert.equal(s.wakes.countExpired("b"), 0);
  assert.equal(s.wakes.rearm("b", null, Date.now()), 0, "no wake target, nothing re-armed");
  s.close();
});

test("only pings that expired before the cut-off are re-armed, and a re-armed old message keeps its place", () => {
  const s = store();
  const old = s.send({ fromAgent: "a", toAgent: "b", body: "old" });
  const newer = s.send({ fromAgent: "a", toAgent: "b", body: "newer" });
  expire(s, old.id, 3 * HOUR); // expired two hours ago
  const twoHoursAgo = Date.now() - 2 * HOUR;
  assert.equal(s.wakes.rearm("b", s.wakes.target("b"), twoHoursAgo - 60_000), 0, "a process older than the expiry");
  assert.equal(s.wakes.rearm("b", s.wakes.target("b"), twoHoursAgo + 60_000), 1);
  // Ordering is by job id, not created_at: the old message goes first although its job was re-created just now.
  const claimed = s.wakes.claim(Date.now() + 1);
  assert.equal(claimed?.messageId, old.id);
  assert.notEqual(claimed?.messageId, newer.id);
  s.close();
});

test("the ping for an old message says when it was first sent and why it comes again", () => {
  const s = store();
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "old" });
  const sent = Date.now() - 2 * HOUR;
  s.database.prepare("UPDATE messages SET created_at = ? WHERE id = ?").run(new Date(sent).toISOString(), message.id);
  expire(s, message.id);
  s.wakes.rearm("b", s.wakes.target("b"), Date.now());
  const text = wakeNotice(job(s, message.id));
  assert.match(text, new RegExp(`first sent at ${clockTime(sent)}`));
  assert.match(text, /not running/);
  assert.match(text, /still applies/);
  const fresh = s.send({ fromAgent: "a", toAgent: "b", body: "new" });
  assert.doesNotMatch(wakeNotice(job(s, fresh.id)), /first sent at/, "a fresh message carries no such line");
  s.close();
});

test("procStart is read as UTC, so a +08:00 clock never flips the comparison", () => {
  // The registry holds `ps -o lstart=` text printed under TZ=UTC.
  assert.equal(parseProcStart("Thu Oct 15 03:00:00 2026"), Date.UTC(2026, 9, 15, 3, 0, 0));
  assert.equal(parseProcStart("Mon Oct  5 03:00:00 2026"), Date.UTC(2026, 9, 5, 3, 0, 0));
  assert.equal(parseProcStart("not a time"), null);
  // A ping that expired at 05:00 UTC (13:00 on a +08:00 Mac) against a process started at 11:00 local = 03:00 UTC:
  // read as local time the process would look later than the expiry; in absolute time it is earlier.
  const s = store();
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "old" });
  const expiredAt = Date.UTC(2026, 9, 15, 5, 0, 0);
  s.database.prepare(`UPDATE wake_jobs SET state = 'expired', pending_reason = 'offline', created_at = ? WHERE message_id = ?`)
    .run(expiredAt - OFFLINE_WAKE_WINDOW_MS, message.id);
  s.database.prepare("UPDATE messages SET expires_at = NULL WHERE id = ?").run(message.id);
  assert.equal(s.wakes.rearm("b", s.wakes.target("b"), parseProcStart("Thu Oct 15 03:00:00 2026")!), 0);
  assert.equal(s.wakes.rearm("b", s.wakes.target("b"), parseProcStart("Thu Oct 15 06:00:00 2026")!), 1);
  s.close();
});

function live(sessionId: string, started: string): ClaudeSession {
  return { pid: 1, sessionId, cwd: "/", name: "b", messagingSocketPath: "/tmp/x.sock", procStart: started,
    version: "1", peerProtocol: 1 };
}

function utcLstart(ms: number): string {
  const d = new Date(ms);
  const day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getUTCDay()];
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()];
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${day} ${month} ${String(d.getUTCDate()).padStart(2, " ")} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} ${d.getUTCFullYear()}`;
}

test("the periodic check re-arms once for a Claude session that started after the expiry", async () => {
  const s = store();
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "old" });
  expire(s, message.id); // expired an hour ago
  let sessions: ClaudeSession[] = [live("claude-b", utcLstart(Date.now() - 90 * 60_000))]; // started before it
  const d = new WakeDispatcher(s, { env: { AGENT_RELAY_NOTIFY: "off" }, claudeSessions: async () => sessions,
    presenceOf: async () => ({ state: "idle" } as never) });
  await d.checkApprovals();
  assert.equal(job(s, message.id).state, "expired", "the process is older than the expiry");

  sessions = [live("claude-b", utcLstart(Date.now() - 60_000))]; // reopened a minute ago
  await d.checkApprovals();
  assert.equal(job(s, message.id).state, "pending", "re-armed after the session came back");
  // It goes offline again and expires: the same process start re-arms nothing more.
  s.database.prepare("UPDATE wake_jobs SET state = 'expired' WHERE message_id = ?").run(message.id);
  await d.checkApprovals();
  assert.equal(job(s, message.id).state, "expired", "once per process start");
  await d.close();
  s.close();
});

test("a re-armed message that goes offline again raises no second offline notice", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-rewake-notice-"));
  const s = store(join(dir, "bridge.sqlite"));
  const message = s.send({ fromAgent: "a", toAgent: "b", body: "old" });
  const log = join(dir, "notices.log");
  // The first offline spell already notified (the D193 mark for this message exists).
  mkdirSync(join(dir, "notified"), { recursive: true });
  writeFileSync(join(dir, "notified", `claude-offline-b-${message.id}`), "");
  expire(s, message.id);
  s.wakes.rearm("b", s.wakes.target("b"), Date.now());
  s.database.prepare("UPDATE wake_jobs SET created_at = ? WHERE message_id = ?").run(Date.now() - 6 * 60_000, message.id);
  const d = new WakeDispatcher(s, { env: { AGENT_RELAY_NOTIFY_LOG: log },
    deliver: async () => ({ state: "pending", reason: "offline", detail: "not running" }) });
  await d.flush();
  assert.equal(job(s, message.id).state, "pending");
  assert.match(job(s, message.id).detail, /A desktop notification was attempted/, "it still says the user was told");
  assert.equal(existsSync(log), false, "no second notice was written");
  await d.close();
  s.close();
});

test("registering again re-arms expired pings and says how many", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-rewake-register-"));
  const codexHome = join(dir, "codex-home");
  mkdirSync(codexHome);
  writeFileSync(join(codexHome, "config.toml"), 'approvals_reviewer = "guardian_subagent"\n');
  const codex = await session(dir, null, { CODEX_HOME: codexHome });
  try {
    assert.ok((await codex.call("bridge_register", { agent: "cx", wake: { app: "codex", sessionId: "thread-cx" } })).ok);
    const s = new BridgeStore(join(dir, "bridge.sqlite"));
    s.register("a");
    const first = s.send({ fromAgent: "a", toAgent: "cx", body: "one" });
    const second = s.send({ fromAgent: "a", toAgent: "cx", body: "two" });
    expire(s, first.id);
    const again = (await codex.call("bridge_register", { agent: "cx", wake: { app: "codex", sessionId: "thread-cx" } })).json();
    assert.equal(again.unread, 2);
    assert.match(again.next, /2 unread message\(s\) are waiting/);
    assert.match(again.next, /1 of them had a background ping that expired while this session was away; it was pinged again/);
    assert.notEqual(s.wakes.forMessage(first.id)?.state, "expired");
    assert.notEqual(s.wakes.forMessage(second.id)?.state, "expired");
    s.close();
  } finally {
    await codex.close();
  }
});
