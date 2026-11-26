import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test, { type TestContext } from "node:test";
import { BridgeStore, type SendInput } from "../src/bridge-store.js";
import type { ClaudeSession } from "../src/claude-wake.js";
import { sweepDeliveryFailures } from "../src/notices.js";
import { sendMessage, type SendContext, type SendRequest } from "../src/send.js";
import * as wakeDispatcher from "../src/wake-dispatcher.js";
import { wakeNotice, type WakeJob, type WakeResult, type WakeTarget } from "../src/wake-queue.js";
import { session } from "./support/session.js";

const HOUR = 3_600_000;
const CLAUDE: WakeTarget = { app: "claude", sessionId: "claude-b" };

function idle(statusUpdatedAt: number): ClaudeSession {
  return { pid: 1, sessionId: CLAUDE.sessionId, cwd: "/", name: "b", messagingSocketPath: "/tmp/test.sock",
    procStart: "", version: "1", peerProtocol: 1, status: "idle", statusUpdatedAt };
}

function fixture(t: TestContext, options: { dbPath?: string; target?: WakeTarget; idleHoldMs?: number;
  env?: NodeJS.ProcessEnv; deliver?: (job: WakeJob) => WakeResult } = {}) {
  const store = new BridgeStore(options.dbPath ?? ":memory:");
  store.register("a");
  store.register("b");
  store.wakes.bind("b", options.target ?? CLAUDE);
  const clock = { now: Date.now() };
  const registry = { sessions: [idle(clock.now - HOUR)] as ClaudeSession[] | null, reads: 0 };
  const delivered: number[] = [];
  const dispatcher = new wakeDispatcher.WakeDispatcher(store, {
    idleHoldMs: options.idleHoldMs ?? HOUR,
    now: () => clock.now,
    env: options.env ?? { AGENT_RELAY_NOTIFY: "off" },
    claudeSessions: async () => {
      registry.reads++;
      return registry.sessions;
    },
    deliver: async (job) => {
      delivered.push(job.messageId);
      return options.deliver?.(job) ?? { state: "accepted", detail: "pinged" };
    },
  });
  t.after(async () => {
    await dispatcher.close();
    store.close();
  });
  return { store, dispatcher, clock, registry, delivered,
    send: (input: Partial<SendInput> = {}) => {
      const message = store.send({ fromAgent: "a", toAgent: "b", body: "a message", ...input });
      clock.now = Math.max(clock.now, Date.now());
      return message;
    },
    job: (messageId: number) => store.wakes.forMessage(messageId)! };
}

test("holds a quiet Claude ping at the idle threshold and keeps the message queued (D299, D301)", async (t) => {
  const { store, dispatcher, clock, registry, delivered, send, job } = fixture(t);
  const message = send();
  registry.sessions = [idle(clock.now - HOUR)];
  await dispatcher.flush();

  const held = job(message.id);
  assert.equal(held.state, "pending");
  assert.equal(held.pendingReason, "idle");
  assert.ok(held.retryAt > held.createdAt + 7 * 24 * HOUR);
  assert.equal(held.detail, "Held, not sent: b's Claude session has been idle for 60 min; the ping goes out " +
    "with its next wake, when the session is active again, or an hour before the message expires.");
  assert.equal(store.messageById(message.id)?.deliveryState, "queued");
  assert.deepEqual(delivered, []);
  assert.equal(registry.reads, 1);
});

const IDLE_WARNING = '"b" has been idle for 60 min; this message needs no reply, so its ping is held and goes out ' +
  "with its next wake (see bridge_outbox).";

test("bridge_send warns when an omitted wake may be held, but not on an idempotent retry (D305)", async (t) => {
  const { store, dispatcher, clock } = fixture(t);
  let reads = 0;
  const context: SendContext = {
    dbPath: ":memory:", presenceOf: async () => ({ state: "unknown" }), env: {}, now: () => clock.now,
    flush: () => {
      clock.now = Math.max(clock.now, Date.now());
      return dispatcher.flush();
    },
    claudeSessions: async () => {
      reads++;
      return [{ ...idle(clock.now - HOUR), sessionId: "primary-claude", bridgeSessionId: CLAUDE.sessionId }];
    },
  };
  const request = { from: "a", to: "b", body: "an update", idempotencyKey: "update" };
  const sent = await sendMessage(store, request, context);
  assert.deepEqual(sent.warnings, [IDLE_WARNING]);
  assert.equal(sent.wake?.pendingReason, "idle");
  assert.equal(sent.deliveryState, "queued");
  assert.equal(sent.bodyLength, request.body.length);
  assert.equal("body" in sent, false);

  const retried = await sendMessage(store, request, context);
  assert.equal(retried.id, sent.id);
  assert.equal(retried.duplicate, true);
  assert.ok(retried.warnings?.length);
  assert.ok(!retried.warnings.includes(IDLE_WARNING));
  assert.equal(reads, 1);
});

const quietSendCases: Array<{
  name: string;
  request?: Partial<SendRequest>;
  target?: WakeTarget;
  env?: NodeJS.ProcessEnv;
  sessions?: (now: number) => ClaudeSession[] | null;
  reads: number;
}> = [
  { name: "expects a reply", request: { expectsReply: true }, reads: 0 },
  { name: "requests an explicit wake", request: { wake: true }, reads: 0 },
  { name: "saves silently", request: { wake: false }, reads: 0 },
  { name: "targets Codex", target: { app: "codex", sessionId: "codex-b" }, reads: 0 },
  { name: "targets an active session", sessions: now => [{ ...idle(now - HOUR), status: "busy" }], reads: 1 },
  { name: "targets a recently idle session", sessions: now => [idle(now - HOUR + 1)], reads: 1 },
  { name: "broadcasts", request: { to: "*" }, reads: 0 },
  { name: "sends to itself", request: { from: "b" }, reads: 0 },
  { name: "disables holding", env: { BRIDGE_IDLE_HOLD_MS: "0" }, reads: 0 },
  { name: "uses a higher threshold", env: { BRIDGE_IDLE_HOLD_MS: String(HOUR * 2) }, reads: 1 },
  { name: "expires in under an hour", request: { expiresInSeconds: 3599 }, reads: 1 },
  { name: "cannot read the registry", sessions: () => null, reads: 1 },
  { name: "encounters a registry read error", sessions: () => { throw new Error("registry unavailable"); }, reads: 1 },
];

for (const { name, request, target, env, sessions, reads } of quietSendCases) {
  test(`bridge_send adds no idle warning when it ${name} (D305)`, async (t) => {
    const { store, clock } = fixture(t, { target });
    let registryReads = 0;
    const sent = await sendMessage(store, { from: "a", to: "b", body: "an update", ...request }, {
      dbPath: ":memory:", presenceOf: async () => ({ state: "unknown" }), flush: async () => {},
      env: env ?? {}, now: () => clock.now,
      claudeSessions: async () => {
        registryReads++;
        return sessions ? sessions(clock.now) : [idle(clock.now - HOUR)];
      },
    });
    assert.equal(sent.warnings, undefined);
    assert.equal(store.messageById(sent.id)?.body, "an update");
    assert.equal(registryReads, reads);
  });
}

test("bridge_outbox keeps idle on the held job and preserves the fallback for other reasons (D305)", async (t) => {
  const { store, dispatcher, clock, send, job } = fixture(t);
  const held = send();
  await dispatcher.flush();
  const ordinary = send({ expectsReply: true });
  const outboxWake = (id: number) => store.outbox("a").entries.find(entry => entry.id === id)?.wake;
  const heldWake = { state: "pending", pendingReason: "idle", detail: job(held.id).detail };
  assert.deepEqual(outboxWake(held.id), heldWake);
  assert.equal(outboxWake(ordinary.id)?.pendingReason, undefined);

  const claimed = store.wakes.claim(clock.now)!;
  assert.equal(claimed.messageId, ordinary.id);
  store.wakes.finish(claimed, { state: "pending", reason: "busy", detail: "Recipient is busy" }, clock.now);
  const queued = send();
  assert.deepEqual(outboxWake(held.id), heldWake);
  assert.equal(outboxWake(ordinary.id)?.pendingReason, "busy");
  assert.equal(outboxWake(queued.id)?.pendingReason, "busy");
});

test("bridge_wake_status reports the held reason and detail by message id and in the list (D305)", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-idle-status-"));
  // The status server has no usable registry, so its periodic check leaves this hold alone.
  mkdirSync(join(dir, ".claude"));
  writeFileSync(join(dir, ".claude", "sessions"), "");
  const { dispatcher, send, job } = fixture(t, { dbPath: join(dir, "bridge.sqlite") });
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const message = send();
  await dispatcher.flush();

  const server = await session(dir, null, { BRIDGE_IDLE_HOLD_MS: String(HOUR) });
  try {
    const single = (await server.call("bridge_wake_status", { messageId: message.id })).json();
    assert.equal(single.deliveryState, "queued");
    assert.equal(single.wake.state, "pending");
    assert.equal(single.wake.pendingReason, "idle");
    assert.equal(single.wake.detail, job(message.id).detail);
    const outbox = (await server.call("bridge_outbox", { agent: "a" })).json();
    assert.deepEqual(outbox.entries.find((entry: { id: number }) => entry.id === message.id)?.wake,
      { state: "pending", pendingReason: "idle", detail: single.wake.detail });
    const list = (await server.call("bridge_wake_status", { agent: "b" })).json();
    assert.deepEqual(list.summary, { pending: 1 });
    assert.deepEqual(list.jobs, [single.wake]);
  } finally {
    await server.close();
  }
});

test("holds a channel ping whose registry entry matches by bridgeSessionId, including a message without expiry", async (t) => {
  const { store, clock, send, job } = fixture(t);
  const message = send();
  store.database.prepare("UPDATE messages SET expires_at = NULL WHERE id = ?").run(message.id);
  let channelPings = 0;
  const dispatcher = new wakeDispatcher.WakeDispatcher(store, {
    now: () => clock.now,
    env: {},
    claudeSessions: async () => [{ ...idle(clock.now - HOUR), sessionId: "primary-claude", bridgeSessionId: CLAUDE.sessionId }],
    channel: { sessionId: CLAUDE.sessionId, send: async () => { channelPings++; } },
  });
  try {
    await dispatcher.flush();
    assert.equal(job(message.id).pendingReason, "idle");
    assert.equal(channelPings, 0);
  } finally {
    await dispatcher.close();
  }
});

const pingCases: Array<{
  name: string;
  input?: Partial<SendInput>;
  target?: WakeTarget;
  idleHoldMs?: number;
  sessions?: (now: number) => ClaudeSession[] | null;
}> = [
  { name: "expects a reply", input: { expectsReply: true } },
  { name: "requests an explicit wake", input: { wake: true } },
  { name: "targets Codex", target: { app: "codex", sessionId: "codex-b" } },
  { name: "targets a busy session", sessions: now => [{ ...idle(now - HOUR), status: "busy" }] },
  { name: "targets a waiting session", sessions: now => [{ ...idle(now - HOUR), status: "waiting" }] },
  { name: "targets a session idle below the threshold", sessions: now => [idle(now - HOUR + 1)] },
  { name: "has no status time", sessions: now => [{ ...idle(now - HOUR), statusUpdatedAt: undefined }] },
  { name: "has a non-finite status time", sessions: () => [idle(-Infinity)] },
  { name: "has an unreadable registry", sessions: () => null },
  { name: "targets a missing session", sessions: now => [{ ...idle(now - HOUR), sessionId: "other" }] },
  { name: "has a zero threshold", idleHoldMs: 0 },
  { name: "expires in under an hour", input: { expiresInSeconds: 3599 } },
];

for (const { name, input, target, idleHoldMs, sessions } of pingCases) {
  test(`pings immediately when the message ${name} (D299)`, async (t) => {
    const { dispatcher, clock, registry, delivered, send, job } = fixture(t, { target, idleHoldMs });
    const message = send(input);
    if (sessions) registry.sessions = sessions(clock.now);
    await dispatcher.flush();

    assert.deepEqual(delivered, [message.id]);
    assert.equal(job(message.id).state, "accepted");
    assert.equal(job(message.id).pendingReason, null);
    if (target?.app === "codex" || idleHoldMs === 0) assert.equal(registry.reads, 0);
  });
}

test("pings immediately when expiry is exactly at the margin (D299)", async (t) => {
  const { store, dispatcher, clock, delivered, send } = fixture(t);
  const message = send();
  store.database.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(clock.now + HOUR, message.id);
  await dispatcher.flush();
  assert.deepEqual(delivered, [message.id]);
});

test("a later ping releases older holds before it sends and stays the only ping in flight (D302, D303b)", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-idle-order-"));
  const dbPath = join(dir, "bridge.sqlite");
  let onSend: () => void = () => {};
  const { store, dispatcher, clock, delivered, send, job } = fixture(t, {
    dbPath, deliver: () => { onSend(); return { state: "accepted", detail: "pinged" }; },
  });
  const other = new BridgeStore(dbPath);
  t.after(() => { other.close(); rmSync(dir, { recursive: true, force: true }); });
  const held = [send(), send()];
  for (const message of held) {
    await dispatcher.flush();
    assert.equal(job(message.id).pendingReason, "idle");
  }
  const urgent = send({ expectsReply: true });
  onSend = () => {
    for (const message of held) {
      assert.equal(job(message.id).pendingReason, null);
      assert.equal(job(message.id).retryAt, clock.now);
      assert.equal(job(message.id).detail, "Released: another ping for this recipient went out");
    }
    assert.equal(other.wakes.claim(clock.now), null);
    store.wakes.recordRead("b", held.map(message => message.id));
  };

  await dispatcher.flush();
  await dispatcher.flush();
  assert.deepEqual(delivered, [urgent.id]);
  for (const message of held) assert.equal(job(message.id).state, "read");
});

for (const [reason, sessions] of [
  ["busy", (now: number) => [{ ...idle(now - HOUR), status: "busy" }]],
  ["waiting", (now: number) => [{ ...idle(now - HOUR), status: "waiting" }]],
  ["recently idle", (now: number) => [idle(now - HOUR + 1)]],
] as const) {
  test(`the periodic check releases a hold when the session becomes ${reason} (D303a)`, async (t) => {
    const { dispatcher, clock, registry, send, job } = fixture(t);
    const message = send();
    await dispatcher.flush();
    assert.equal(job(message.id).pendingReason, "idle");

    registry.sessions = sessions(clock.now);
    await dispatcher.checkHeld();
    assert.equal(job(message.id).state, "pending");
    assert.equal(job(message.id).pendingReason, null);
    assert.equal(job(message.id).retryAt, clock.now);
    assert.match(job(message.id).detail, /^Released: /);
    assert.equal(registry.reads, 2);
  });
}

test("a stopped session releases to the usual offline path (D303a)", async (t) => {
  const { dispatcher, registry, delivered, send, job } = fixture(t, {
    deliver: () => ({ state: "pending", reason: "offline", detail: "Claude session is not running" }),
  });
  const message = send();
  await dispatcher.flush();
  assert.equal(job(message.id).pendingReason, "idle");

  registry.sessions = [];
  await dispatcher.checkHeld();
  await dispatcher.flush();
  assert.deepEqual(delivered, [message.id]);
  assert.equal(job(message.id).state, "pending");
  assert.equal(job(message.id).pendingReason, "offline");
});

test("an unreadable registry preserves holds until one of the agent's messages nears expiry (D303c)", async (t) => {
  const { store, dispatcher, clock, registry, delivered, send, job } = fixture(t);
  store.wakes.bind("c", { app: "claude", sessionId: "claude-c" });
  registry.sessions!.push({ ...idle(clock.now - HOUR), sessionId: "claude-c" });
  const near = send({ expiresInSeconds: 3 * 3600 });
  const far = send();
  const otherAgent = send({ toAgent: "c" });
  for (const message of [near, far, otherAgent]) {
    await dispatcher.flush();
    assert.equal(job(message.id).pendingReason, "idle");
  }

  registry.sessions = null;
  await dispatcher.checkHeld();
  assert.equal(job(near.id).pendingReason, "idle");
  clock.now = Date.parse(near.expiresAt!) - HOUR;
  await dispatcher.checkHeld();
  assert.equal(registry.reads, 5);
  for (const message of [near, far]) {
    assert.equal(job(message.id).state, "pending");
    assert.equal(job(message.id).pendingReason, null);
  }
  assert.equal(job(otherAgent.id).pendingReason, "idle");
  await dispatcher.flush();
  await dispatcher.flush();
  assert.deepEqual(delivered, [near.id, far.id], "old holds can be sent even after the original retry window");
});

test("a released job is sent even if its session is still idle past the threshold (D303)", async (t) => {
  const { store, dispatcher, clock, registry, delivered, send, job } = fixture(t, {
    deliver: () => ({ state: "pending", reason: "busy", detail: "mid-turn" }),
  });
  const message = send();
  await dispatcher.flush();
  assert.equal(job(message.id).pendingReason, "idle");

  clock.now += 2 * HOUR;
  registry.sessions = [{ ...idle(clock.now), status: "busy" }];
  await dispatcher.checkHeld();
  assert.equal(store.database.prepare("SELECT explicit_wake FROM wake_jobs WHERE message_id = ?")
    .get(message.id)?.explicit_wake, 2);
  registry.sessions = [idle(clock.now - 3 * HOUR)];
  await dispatcher.flush();
  assert.deepEqual(delivered, [message.id]);
  assert.equal(job(message.id).pendingReason, "busy");
  clock.now = Math.max(clock.now, job(message.id).retryAt);
  await dispatcher.flush();
  assert.deepEqual(delivered, [message.id, message.id]);
  assert.doesNotMatch(wakeNotice(job(message.id)), /earlier ping expired|was not running/);
});

test("starting with the threshold disabled releases every held agent (D303d)", async (t) => {
  const { store, dispatcher, clock, registry, send, job } = fixture(t);
  store.wakes.bind("c", { app: "claude", sessionId: "claude-c" });
  registry.sessions!.push({ ...idle(clock.now - HOUR), sessionId: "claude-c" });
  const messages = [send(), send({ toAgent: "c" })];
  for (const message of messages) {
    await dispatcher.flush();
    assert.equal(job(message.id).pendingReason, "idle");
  }
  let reads = 0;
  const restarted = new wakeDispatcher.WakeDispatcher(store, {
    idleHoldMs: 0, now: () => clock.now,
    claudeSessions: async () => { reads++; return registry.sessions; },
    deliver: async () => ({ state: "accepted", detail: "pinged" }),
  });
  try {
    restarted.start();
    await restarted.flush();
    await restarted.flush();
    assert.equal(reads, 0);
    for (const message of messages) assert.equal(job(message.id).state, "accepted");
  } finally {
    await restarted.close();
  }
});

test("the 30-second tick checks holds even when approval checking has no work (D303a)", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const { store, dispatcher, clock, registry, send, job } = fixture(t);
  const message = send();
  await dispatcher.flush();
  assert.equal(job(message.id).pendingReason, "idle");
  t.mock.method(store, "claudeWaiting", () => []);
  registry.sessions = [];
  dispatcher.start();
  clock.now += 30_000;
  t.mock.timers.tick(2000);
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(registry.reads, 2);
  assert.equal(job(message.id).pendingReason, null);
});

test("approval and hold checks share one Claude registry read per tick (D303a)", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const { dispatcher, clock, registry, send, job } = fixture(t);
  const message = send();
  await dispatcher.flush();
  assert.equal(job(message.id).pendingReason, "idle");
  dispatcher.start();
  clock.now += 30_000;
  t.mock.timers.tick(2000);
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(registry.reads, 2);
  assert.equal(job(message.id).pendingReason, "idle");
});

test("holds survive the pending wake windows until the message itself expires (D302)", async (t) => {
  const { store, dispatcher, clock, delivered, send, job } = fixture(t);
  const message = send({ expiresInSeconds: 2 * 24 * 3600 });
  await dispatcher.flush();
  assert.equal(job(message.id).pendingReason, "idle");
  clock.now += 25 * HOUR;
  await dispatcher.flush();
  assert.equal(job(message.id).state, "pending");
  assert.equal(job(message.id).pendingReason, "idle");
  assert.equal(store.messageById(message.id)?.deliveryState, "queued");

  clock.now = Date.parse(message.expiresAt!);
  await dispatcher.flush();
  assert.equal(store.messageById(message.id)?.deliveryState, "expired");
  assert.equal(job(message.id).state, "expired");
  assert.match(job(message.id).detail, /Message expired before delivery/);
  assert.deepEqual(delivered, []);
});

test("acknowledging a held message closes its wake job (D302)", async (t) => {
  const { store, dispatcher, registry, delivered, send, job } = fixture(t);
  const message = send();
  await dispatcher.flush();
  assert.equal(job(message.id).pendingReason, "idle");

  assert.equal(store.ack("b", [message.id]), 1);
  registry.sessions = [];
  await dispatcher.checkHeld();
  await dispatcher.flush();
  assert.equal(job(message.id).state, "acknowledged");
  assert.deepEqual(delivered, []);
});

test("an acknowledgement during the registry read prevents dispatch of the claimed wake", async (t) => {
  const { store, clock, send, job } = fixture(t);
  const message = send();
  let deliveries = 0;
  const dispatcher = new wakeDispatcher.WakeDispatcher(store, {
    idleHoldMs: HOUR, now: () => clock.now,
    claudeSessions: async () => { store.ack("b", [message.id]); return null; },
    deliver: async () => { deliveries++; return { state: "accepted", detail: "pinged" }; },
  });
  try {
    await dispatcher.flush();
    assert.equal(job(message.id).state, "acknowledged");
    assert.equal(deliveries, 0);
  } finally {
    await dispatcher.close();
  }
});

test("a held ping sends neither a desktop notice nor a bridge failure notice (D306)", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-idle-notice-"));
  const log = join(dir, "notices.log");
  const { store, dispatcher, clock, delivered, send, job } = fixture(t, {
    dbPath: join(dir, "bridge.sqlite"), env: { AGENT_RELAY_NOTIFY_LOG: log },
    deliver: () => ({ state: "pending", reason: "offline", detail: "not running" }),
  });
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const message = send();
  store.database.prepare("UPDATE wake_jobs SET created_at = ? WHERE message_id = ?")
    .run(clock.now - 10 * 60_000, message.id);
  await dispatcher.flush();
  assert.equal(job(message.id).pendingReason, "idle");
  clock.now += 2 * HOUR;
  await dispatcher.flush();
  assert.equal(sweepDeliveryFailures(store, clock.now), 0);
  assert.equal(existsSync(log), false);
  assert.deepEqual(store.inbox("a"), []);
  assert.deepEqual(delivered, []);
});

test("BRIDGE_IDLE_HOLD_MS accepts zero or an in-range whole number (D304)", () => {
  const parse = wakeDispatcher.idleHoldMs;
  assert.equal(parse({}), HOUR);
  for (const [raw, ms] of [["0", 0], ["60000", 60_000], ["7200000", 7_200_000], ["86400000", 86_400_000]] as const) {
    assert.equal(parse({ BRIDGE_IDLE_HOLD_MS: raw }), ms, raw);
  }
  for (const raw of ["", "-1", "00", "59999", "86400001", "60000.0", "60000ms", "6e4", " 60000 ", "invalid"]) {
    assert.equal(parse({ BRIDGE_IDLE_HOLD_MS: raw }), HOUR, raw);
  }
});

test("a wake job an older bridge inserted without explicit_wake is never held (review of D300)", async (t) => {
  const { store, dispatcher, delivered, send, job } = fixture(t);
  const message = send({ wake: false });
  const now = Date.now();
  // 0.10.x's enqueue leaves explicit_wake out, so the column default applies.
  store.database.prepare(`INSERT INTO wake_jobs (message_id, agent, target, retry_at, created_at) VALUES (?, ?, ?, ?, ?)`)
    .run(message.id, "b", JSON.stringify(CLAUDE), now, now);
  await dispatcher.flush();

  assert.deepEqual(delivered, [message.id]);
  assert.notEqual(job(message.id).pendingReason, "idle");
});

test("a hold that cannot be written still sends the ping (review of D301)", async (t) => {
  const { store, dispatcher, delivered, send } = fixture(t);
  store.wakes.holdIdle = () => { throw new Error("database is locked"); };
  const message = send();
  await dispatcher.flush();

  assert.deepEqual(delivered, [message.id]);
});

test("a release that cannot be written still sends the urgent ping (review of D303b)", async (t) => {
  const { store, dispatcher, delivered, send } = fixture(t);
  store.wakes.releaseHeld = () => { throw new Error("database is locked"); };
  const message = send({ expectsReply: true });
  await dispatcher.flush();

  assert.deepEqual(delivered, [message.id]);
});
