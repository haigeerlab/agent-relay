// agent-relay presence-and-approval D148: the user hears, once per waiting episode, that a mailbox session waits for
// their approval while a message to it is unhandled. The bridge only tells; it never answers the prompt.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { noticeFields } from "../src/notify.js";
import type { Presence } from "../src/presence.js";
import { WakeDispatcher } from "../src/wake-dispatcher.js";

function setup() {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-approval-"));
  const store = new BridgeStore(join(dir, "bridge.sqlite"));
  store.register("sender");
  store.register("cc", undefined, { app: "claude", sessionId: "host-cc" });
  store.wakes.bind("cc", { app: "claude", sessionId: "host-cc" });
  // presence-polish D176: hosted in Claude but not bound to wake; the approval check leaves it alone.
  store.register("unbound", undefined, { app: "claude", sessionId: "host-unbound" });
  store.register("bound");
  store.wakes.bind("bound", { app: "claude", sessionId: "wake-bound" });
  store.register("cx", undefined, { app: "codex", sessionId: "thread-cx" });
  const log = join(dir, "notices.log");
  const lines = () => (existsSync(log) ? readFileSync(log, "utf8").trim().split("\n").filter(Boolean) : []);
  return { dir, store, log, lines, env: { AGENT_RELAY_NOTIFY_LOG: log } as NodeJS.ProcessEnv };
}

test("the store lists, per wake-bound Claude agent, its oldest unhandled direct message", () => {
  const { store } = setup();
  store.send({ fromAgent: "sender", toAgent: "unbound", body: "not checked" });
  const first = store.send({ fromAgent: "sender", toAgent: "cc", body: "one" });
  store.send({ fromAgent: "sender", toAgent: "cc", body: "two" });
  const bound = store.send({ fromAgent: "sender", toAgent: "bound", body: "three" });
  store.send({ fromAgent: "sender", toAgent: "cx", body: "codex" });
  store.send({ fromAgent: "sender", toAgent: "*", body: "broadcast" });
  assert.deepEqual(store.claudeWaiting(), [
    { agent: "bound", sessionId: "wake-bound", messageId: bound.id, fromAgent: "sender" },
    { agent: "cc", sessionId: "host-cc", messageId: first.id, fromAgent: "sender" },
  ]);
  store.ack("cc", [first.id]);
  assert.equal(store.claudeWaiting().find((w) => w.agent === "cc")?.messageId, first.id + 1);
  store.close();
});

test("one notice per waiting episode, none once handled, none when the session is not waiting", async () => {
  const { store, lines, env } = setup();
  let presence: Presence = { state: "waiting-approval", since: "2026-10-09T02:12:10.000Z", detail: "permission prompt" };
  const asked: string[] = [];
  const d = new WakeDispatcher(store, { env, deliver: async () => ({ state: "unknown", detail: "test" }),
    presenceOf: async (sessionId) => { asked.push(sessionId); return presence; } });
  const message = store.send({ fromAgent: "sender", toAgent: "cc", body: "please review" });

  await d.checkApprovals();
  assert.deepEqual(asked, ["host-cc"]);
  assert.equal(lines().length, 1);
  assert.match(lines()[0], /cc is waiting for your approval/);
  assert.match(lines()[0], /"sender"/);
  assert.doesNotMatch(lines()[0], /please review/, "the notice does not carry the message");

  await d.checkApprovals();
  assert.equal(lines().length, 1, "same episode: not again");

  presence = { state: "running" };
  await d.checkApprovals();
  presence = { state: "waiting-approval", since: "2026-10-09T03:00:00.000Z", detail: "permission prompt" };
  await d.checkApprovals();
  assert.equal(lines().length, 2, "a new episode is told again");

  store.ack("cc", [message.id]);
  presence = { state: "waiting-approval", since: "2026-10-09T04:00:00.000Z" };
  await d.checkApprovals();
  assert.equal(lines().length, 2, "nothing waits for it any more");
  await d.close();
  store.close();
});

test("other states and switched-off notices stay quiet", async () => {
  for (const state of ["running", "waiting-input", "stopped", "unknown"] as const) {
    const { store, lines, env } = setup();
    store.send({ fromAgent: "sender", toAgent: "cc", body: "x" });
    const d = new WakeDispatcher(store, { env, deliver: async () => ({ state: "unknown", detail: "test" }),
      presenceOf: async () => ({ state }) });
    await d.checkApprovals();
    assert.deepEqual(lines(), [], state);
    await d.close();
    store.close();
  }
  const { store, lines, log } = setup();
  store.send({ fromAgent: "sender", toAgent: "cc", body: "x" });
  const d = new WakeDispatcher(store, { env: { AGENT_RELAY_NOTIFY: "off", AGENT_RELAY_NOTIFY_LOG: log },
    deliver: async () => ({ state: "unknown", detail: "test" }),
    presenceOf: async () => ({ state: "waiting-approval", since: "t" }) });
  await d.checkApprovals();
  assert.deepEqual(lines(), []);
  await d.close();
  store.close();
});

test("the approval notice names the session and the sender and offers no action", () => {
  const notice = { kind: "approval" as const, messageId: 9, fromAgent: "sender", agent: "cc",
    why: "waiting for your approval in its Claude session" };
  for (const preview of [true, false]) {
    const fields = noticeFields(notice, { preview });
    assert.match(fields.title, /^agent-relay/);
    assert.equal(`${fields.title} ${fields.subtitle} ${fields.body}`.includes("Codex"), false, JSON.stringify(fields));
    assert.match(fields.body, /cc is waiting for your approval in its Claude session/);
    assert.match(fields.body, /message #9 from "sender" waits/);
    assert.doesNotMatch(fields.body, /approve|allow|click/i);
  }
});

test("without statusUpdatedAt each waiting episode is still told once, across every bridge on the mailbox", async () => {
  // agent-relay presence-polish D175: Claude Code may not write statusUpdatedAt; the episode then starts when a bridge
  // first sees the session waiting, recorded next to the notice marks so every bridge uses the same key.
  const { store, lines, env } = setup();
  let presence: Presence = { state: "waiting-approval", detail: "permission prompt" };
  const options = { env, deliver: async () => ({ state: "unknown" as const, detail: "test" }),
    presenceOf: async () => presence };
  const first = new WakeDispatcher(store, options);
  const second = new WakeDispatcher(store, options);
  store.send({ fromAgent: "sender", toAgent: "cc", body: "please review" });

  await first.checkApprovals();
  await second.checkApprovals();
  await first.checkApprovals();
  assert.equal(lines().length, 1, "one episode, two bridges: one notice");

  presence = { state: "running" };
  await second.checkApprovals();
  presence = { state: "waiting-approval", detail: "permission prompt" };
  await new Promise((resolve) => setTimeout(resolve, 5));
  await first.checkApprovals();
  await second.checkApprovals();
  assert.equal(lines().length, 2, "a new episode is told again");

  // The session leaves the list once its message is handled, so nothing ends the episode there; a later message that
  // waits is still told.
  const [waitingNow] = store.claudeWaiting();
  store.ack("cc", [waitingNow.messageId]);
  await first.checkApprovals();
  store.send({ fromAgent: "sender", toAgent: "cc", body: "one more" });
  await first.checkApprovals();
  await second.checkApprovals();
  assert.equal(lines().length, 3, "a new message waiting is told once");
  await first.close();
  await second.close();
  store.close();
});

test("housekeeping removes the episode marks of sessions with nothing waiting", async () => {
  // agent-relay install-docs-accuracy D180 (review of #66): a handled message takes its session off the waiting list,
  // so nothing saw that episode end; the Housekeeper clears such marks and keeps the ones still waiting.
  const { Housekeeper } = await import("../src/housekeeping.js");
  const { writeFileSync, mkdirSync, readdirSync } = await import("node:fs");
  const { dir, store } = setup();
  store.send({ fromAgent: "sender", toAgent: "cc", body: "still waiting" });
  const marks = join(dir, "notified");
  mkdirSync(marks, { recursive: true });
  const { utimesSync } = await import("node:fs");
  const old = new Date(Date.now() - 11 * 60_000);
  for (const name of ["episode-host-cc", "episode-gone-session", "approval-host-cc-1-2"]) {
    writeFileSync(join(marks, name), "1");
    utimesSync(join(marks, name), old, old);
  }
  // Just written by a bridge that saw a new message the Housekeeper's list did not have yet: left alone.
  writeFileSync(join(marks, "episode-just-started"), "1");
  await new Housekeeper(store).tick();
  assert.deepEqual(readdirSync(marks).sort(), ["approval-host-cc-1-2", "episode-host-cc", "episode-just-started"]);
  store.close();
});

// agent-relay notice-location D188: the approval notice says where the waiting session is, looked up once per notice.
test("the approval notice names the session's place, and a notice already shown costs no second lookup", async () => {
  const { store, lines, env } = setup();
  const located: string[] = [];
  const d = new WakeDispatcher(store, { env, deliver: async () => ({ state: "unknown", detail: "test" }),
    presenceOf: async () => ({ state: "waiting-approval", since: "2026-10-10T06:00:00.000Z" }),
    locationOf: async (sessionId) => { located.push(sessionId);
      return { place: { kind: "terminal", tty: "ttys003", bundle: "com.apple.Terminal", app: "Terminal" },
        session: "fix gate", project: "agent-relay" }; } });
  store.send({ fromAgent: "sender", toAgent: "cc", body: "please review" });
  await d.checkApprovals();
  await d.checkApprovals();
  assert.equal(lines().length, 1);
  assert.match(lines()[0], /· cc · fix gate in agent-relay · Terminal ttys003 \|/);
  assert.deepEqual(located, ["host-cc"], "looked up once");
  await d.close();
  store.close();
});

// Review of #84: with notices switched off no mark is ever written, so the place must not be looked up every 30 s.
test("switched-off notices never look the place up", async () => {
  for (const off of ["env", "file"] as const) {
    const { store, lines, log, dir } = setup();
    if (off === "file") writeFileSync(join(dir, "notify.off"), "");
    const located: string[] = [];
    const d = new WakeDispatcher(store, {
      env: { AGENT_RELAY_NOTIFY_LOG: log, ...(off === "env" ? { AGENT_RELAY_NOTIFY: "off" } : {}) },
      deliver: async () => ({ state: "unknown", detail: "test" }),
      presenceOf: async () => ({ state: "waiting-approval", since: "t" }),
      locationOf: async (sessionId) => { located.push(sessionId); return undefined; } });
    store.send({ fromAgent: "sender", toAgent: "cc", body: "x" });
    await d.checkApprovals();
    await d.checkApprovals();
    assert.deepEqual([lines(), located], [[], []], off);
    await d.close();
    store.close();
  }
});
