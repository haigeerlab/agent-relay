// agent-relay presence-and-approval D148: the user hears, once per waiting episode, that a mailbox session waits for
// their approval while a message to it is unhandled. The bridge only tells; it never answers the prompt.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
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
  store.register("bound");
  store.wakes.bind("bound", { app: "claude", sessionId: "wake-bound" });
  store.register("cx", undefined, { app: "codex", sessionId: "thread-cx" });
  const log = join(dir, "notices.log");
  const lines = () => (existsSync(log) ? readFileSync(log, "utf8").trim().split("\n").filter(Boolean) : []);
  return { dir, store, log, lines, env: { AGENT_RELAY_NOTIFY_LOG: log } as NodeJS.ProcessEnv };
}

test("the store lists, per Claude-hosted agent, its oldest unhandled direct message", () => {
  const { store } = setup();
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
