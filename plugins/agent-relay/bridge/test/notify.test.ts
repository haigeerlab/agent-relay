// agent-relay codex-gated-wake D67: the user hears about Codex messages that cannot be delivered, once per message.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { BUSY_NOTIFY_AFTER_MS, notifyUndelivered } from "../src/notify.js";
import { WakeDispatcher } from "../src/wake-dispatcher.js";
import type { WakeResult } from "../src/wake-queue.js";
import { session } from "./support/session.js";

function setup(target: "codex" | "claude" = "codex") {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-notify-"));
  const store = new BridgeStore(join(dir, "bridge.sqlite"));
  store.register("sender");
  store.register("cx");
  store.wakes.bind("cx", { app: target, sessionId: "thread-cx" });
  const log = join(dir, "notices.log");
  const lines = () => (existsSync(log) ? readFileSync(log, "utf8").trim().split("\n").filter(Boolean) : []);
  return { dir, store, log, lines };
}

function dispatcher(store: BridgeStore, log: string, results: WakeResult[], extra: NodeJS.ProcessEnv = {}) {
  return new WakeDispatcher(store, {
    deliver: async () => results.shift() ?? { state: "pending", detail: "offline", reason: "offline" },
    env: { AGENT_RELAY_NOTIFY_LOG: log, ...extra },
  });
}

test("an offline Codex recipient notifies once, without the body, and the wake detail says so", async () => {
  const { dir, store, log, lines } = setup();
  const message = store.send({ fromAgent: "sender", toAgent: "cx", body: "secret body" });
  const d = dispatcher(store, log, [
    { state: "pending", detail: "Codex local connection unavailable", reason: "offline" },
  ]);
  await d.flush();
  assert.equal(lines().length, 1);
  assert.match(lines()[0], new RegExp(`"sender" gave Codex work: message #${message.id} to "cx"`));
  assert.doesNotMatch(lines()[0], /secret/);
  assert.match(store.wakes.forMessage(message.id)?.detail ?? "", /The user was notified on this Mac/);
  // Any other bridge on the same mailbox never notifies the same message again.
  assert.equal(notifyUndelivered(join(dir, "bridge.sqlite"),
    { messageId: message.id, fromAgent: "sender", agent: "cx", why: "again" }, { AGENT_RELAY_NOTIFY_LOG: log }), false);
  assert.equal(lines().length, 1);
  await d.close();
  store.close();
});

test("held notifies at once", async () => {
  const { store, log, lines } = setup();
  store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
  const d = dispatcher(store, log, [{ state: "held", detail: "gate unverified" }]);
  await d.flush();
  assert.equal(lines().length, 1);
  await d.close();
  store.close();
});

test("busy notifies only after ten minutes, once, and never when delivered sooner", async () => {
  assert.equal(BUSY_NOTIFY_AFTER_MS, 600_000);
  const { store, log, lines } = setup();
  const early = store.send({ fromAgent: "sender", toAgent: "cx", body: "a" });
  const d = dispatcher(store, log, [
    { state: "pending", detail: "busy", reason: "busy" },
  ]);
  await d.flush();
  assert.equal(lines().length, 0, "busy for less than ten minutes is silent");
  // Delivered within ten minutes: never notified.
  store.database.prepare("UPDATE wake_jobs SET retry_at = 0 WHERE message_id = ?").run(early.id);
  const delivered = dispatcher(store, log, [{ state: "accepted", detail: "ok" }]);
  await delivered.flush();
  assert.equal(store.wakes.forMessage(early.id)?.state, "accepted");
  assert.equal(lines().length, 0);
  await delivered.close();

  // Pings to one recipient go in order, so the late message goes to a second Codex recipient.
  store.register("cx2");
  store.wakes.bind("cx2", { app: "codex", sessionId: "thread-cx2" });
  const late = store.send({ fromAgent: "sender", toAgent: "cx2", body: "b" });
  store.database.prepare("UPDATE wake_jobs SET created_at = ? WHERE message_id = ?")
    .run(Date.now() - BUSY_NOTIFY_AFTER_MS - 1000, late.id);
  const d2 = dispatcher(store, log, [
    { state: "pending", detail: "busy", reason: "busy" },
    { state: "pending", detail: "busy", reason: "busy" },
  ]);
  await d2.flush();
  assert.equal(lines().length, 1);
  assert.match(lines()[0], new RegExp(`message #${late.id}`));
  store.database.prepare("UPDATE wake_jobs SET retry_at = 0 WHERE message_id = ?").run(late.id);
  await d2.flush();
  assert.equal(lines().length, 1, "once per message");
  await Promise.all([d.close(), d2.close()]);
  store.close();
});

test("the switch turns notifications off, and Claude recipients are never notified", async () => {
  for (const [label, env, file] of [["env", { AGENT_RELAY_NOTIFY: "off" }, false], ["file", {}, true]] as const) {
    const { dir, store, log, lines } = setup();
    if (file) writeFileSync(join(dir, "notify.off"), "");
    store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
    const d = dispatcher(store, log, [{ state: "held", detail: "x" }], env);
    await d.flush();
    assert.equal(lines().length, 0, label);
    await d.close();
    store.close();
  }
  const { store, log, lines } = setup("claude");
  store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
  const d = dispatcher(store, log, [{ state: "pending", detail: "offline", reason: "offline" }]);
  await d.flush();
  assert.equal(lines().length, 0);
  await d.close();
  store.close();
});

test("a Codex recipient with no wake binding notifies at send time and the sender is told", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-notify-send-"));
  const log = join(dir, "notices.log");
  const env = { AGENT_RELAY_NOTIFY: "", AGENT_RELAY_NOTIFY_LOG: log };
  // A Codex identity whose host is recorded but which has no wake binding.
  const prepared = new BridgeStore(join(dir, "bridge.sqlite"));
  prepared.register("cx", [], { app: "codex", sessionId: "thread-cx" });
  prepared.close();
  const sender = await session(dir, "claude-sender", env);
  try {
    assert.ok((await sender.call("bridge_register", { agent: "sender" })).ok);
    const sent = await sender.call("bridge_send", { from: "sender", to: "cx", body: "secret work" });
    assert.ok(sent.ok, sent.text);
    assert.ok(sent.json().warnings.some((w: string) => /The user was notified on this Mac/.test(w)), sent.text);
    const lines = readFileSync(log, "utf8").trim().split("\n");
    assert.equal(lines.length, 1);
    assert.doesNotMatch(lines[0], /secret/);
    const silent = await sender.call("bridge_send", { from: "sender", to: "cx", body: "quiet", wake: false });
    assert.ok(silent.ok);
    assert.equal(readFileSync(log, "utf8").trim().split("\n").length, 1, "wake: false stays silent");
  } finally {
    await sender.close();
  }
});

test("a recipient with no wake binding and no known host warns the sender, without a notification (D72)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-unbound-"));
  const log = join(dir, "notices.log");
  const env = { AGENT_RELAY_NOTIFY: "", AGENT_RELAY_NOTIFY_LOG: log };
  const UNBOUND = /"cx2" has no wake binding and no known host; it sees this message only when it reads its inbox\./;
  const codex = await session(dir, null, env);
  try {
    // Found in the 0.3.0 acceptance: a Codex task registered with wake: null records no host.
    const registered = await codex.call("bridge_register", { agent: "cx2", wake: null });
    assert.ok(registered.ok, registered.text);
  } finally {
    await codex.close();
  }
  const prepared = new BridgeStore(join(dir, "bridge.sqlite"));
  prepared.register("helper", [], { app: "claude", sessionId: "claude-helper" });
  prepared.close();
  const sender = await session(dir, "claude-sender", env);
  try {
    assert.ok((await sender.call("bridge_register", { agent: "sender" })).ok);
    const sent = await sender.call("bridge_send", { from: "sender", to: "cx2", body: "work", idempotencyKey: "k1" });
    assert.ok(sent.ok, sent.text);
    assert.ok(sent.json().warnings?.some((w: string) => UNBOUND.test(w)), sent.text);
    const again = await sender.call("bridge_send", { from: "sender", to: "cx2", body: "work", idempotencyKey: "k1" });
    assert.ok(again.json().duplicate, again.text);
    assert.ok(!(again.json().warnings ?? []).some((w: string) => UNBOUND.test(w)), "a duplicate does not warn again");
    const quiet = await sender.call("bridge_send", { from: "sender", to: "cx2", body: "quiet", wake: false });
    assert.ok(!(quiet.json().warnings ?? []).some((w: string) => UNBOUND.test(w)), "wake: false stays silent");
    const all = await sender.call("bridge_send", { from: "sender", to: "*", body: "everyone" });
    assert.ok(all.ok, all.text);
    assert.ok(!(all.json().warnings ?? []).some((w: string) => /no known host/.test(w)), "a broadcast stays silent");
    const helper = await sender.call("bridge_send", { from: "sender", to: "helper", body: "poll" });
    assert.ok(helper.ok, helper.text);
    assert.ok(!(helper.json().warnings ?? []).some((w: string) => /no known host/.test(w)), "a known Claude host stays silent");
    assert.equal(existsSync(log), false, "never a desktop notification");
  } finally {
    await sender.close();
  }
});
