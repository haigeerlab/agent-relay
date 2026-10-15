// agent-relay codex-gated-wake D67: the user hears about Codex messages that cannot be delivered, once per message.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { BUSY_NOTIFY_AFTER_MS, CLAUDE_OFFLINE_NOTIFY_AFTER_MS, NAME_CHARS, clockTime, noticeFields, notifyUndelivered, PREVIEW_CHARS,
  REASON_CHARS } from "../src/notify.js";
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

test("an offline Codex recipient notifies once with a short preview, and the wake detail says so", async () => {
  const { dir, store, log, lines } = setup();
  const message = store.send({ fromAgent: "sender", toAgent: "cx", body: "secret body" });
  const d = dispatcher(store, log, [
    { state: "pending", detail: "Codex local connection unavailable", reason: "offline" },
  ]);
  await d.flush();
  assert.equal(lines().length, 1);
  // agent-relay notify-channel D89 (reverses D67's "never the body"): title, subtitle and a cleaned preview.
  assert.equal(lines()[0], `agent-relay · sender → Codex | #${message.id} · cx · Codex is not running; the message waits | secret body`);
  assert.match(store.wakes.forMessage(message.id)?.detail ?? "", /A desktop notification was attempted on this Mac; macOS may not show it \(notifications not allowed for the app that shows them, or Focus\)\. The user can list waiting messages with doctor or by asking any session\./);
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
  assert.match(lines()[0], new RegExp(`#${late.id} · cx2 · Codex has been busy for ten minutes`));
  store.database.prepare("UPDATE wake_jobs SET retry_at = 0 WHERE message_id = ?").run(late.id);
  await d2.flush();
  assert.equal(lines().length, 1, "once per message");
  await Promise.all([d.close(), d2.close()]);
  store.close();
});

test("the switch turns notifications off, and a Claude recipient offline for less than five minutes is not notified", async () => {
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

// claude-offline-notice D193: a Claude recipient whose session is not running is told to the user once per offline
// spell, after five minutes: which session, how many messages wait, when the first was sent. No body, no click.
function age(store: BridgeStore, messageId: number, ms: number) {
  store.database.prepare("UPDATE wake_jobs SET created_at = ?, retry_at = 0 WHERE message_id = ?")
    .run(Date.now() - ms, messageId);
}
const offline: WakeResult = { state: "pending", detail: "not running", reason: "offline" };

test("a Claude recipient offline for five minutes notifies once per spell, naming the session, count and first time", async () => {
  assert.equal(CLAUDE_OFFLINE_NOTIFY_AFTER_MS, 300_000);
  const { store, log, lines } = setup("claude");
  const first = store.send({ fromAgent: "sender", toAgent: "cx", body: "secret body" });
  const second = store.send({ fromAgent: "sender", toAgent: "cx", body: "another" });
  age(store, first.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS - 60_000);
  const d = dispatcher(store, log, []);
  await d.flush();
  assert.equal(lines().length, 0, "four minutes: silent");

  const sentAt = Date.now() - CLAUDE_OFFLINE_NOTIFY_AFTER_MS - 1000;
  age(store, first.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 1000);
  await d.flush();
  assert.equal(lines().length, 1);
  const time = clockTime(sentAt);
  assert.equal(lines()[0], `agent-relay · cx is offline | Claude · 2 waiting · first sent ${time} | ` +
    `Claude session "cx" is not running (the Claude app may have stopped it while idle). 2 messages cannot be ` +
    `delivered; the first, #${first.id} from "sender", was sent at ${time}. Open that session to deliver them.`);
  assert.doesNotMatch(lines()[0], /secret body|another/, "never the message text");
  assert.match(store.wakes.forMessage(first.id)?.detail ?? "", /A desktop notification was attempted on this Mac/);
  assert.equal(store.wakes.forMessage(second.id)?.state, "pending");

  // More retries and another message in the same spell: no second notice.
  store.send({ fromAgent: "sender", toAgent: "cx", body: "third" });
  age(store, first.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 120_000);
  await d.flush();
  assert.equal(lines().length, 1, "once per spell");

  // The session comes back and takes every message; a later spell notifies again.
  store.ack("cx", store.inbox("cx", { limit: 10 }).map((message) => message.id));
  const later = store.send({ fromAgent: "sender", toAgent: "cx", body: "later" });
  age(store, later.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 1000);
  await d.flush();
  assert.equal(lines().length, 2, "a new spell notifies again");
  assert.ok(lines()[1].includes(`Claude · 1 waiting`) && lines()[1].includes(`1 message cannot be delivered; the first, #${later.id} from "sender"`), lines()[1]);
  await d.close();
  store.close();
});

test("a Claude notice has no click action and respects the switches; other Claude results stay silent", async () => {
  for (const [label, env, file] of [["env", { AGENT_RELAY_NOTIFY: "off" }, false], ["file", {}, true]] as const) {
    const { dir, store, log, lines } = setup("claude");
    if (file) writeFileSync(join(dir, "notify.off"), "");
    const m = store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
    age(store, m.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 1000);
    const d = dispatcher(store, log, [offline], env);
    await d.flush();
    assert.equal(lines().length, 0, label);
    await d.close();
    store.close();
  }
  for (const result of [{ state: "held", detail: "held for approval" }, { state: "accepted", detail: "ok" },
    { state: "refused", detail: "no" }, { state: "unknown", detail: "?" }] as WakeResult[]) {
    const { store, log, lines } = setup("claude");
    const m = store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
    age(store, m.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 1000);
    const d = dispatcher(store, log, [result]);
    await d.flush();
    assert.equal(lines().length, 0, result.state);
    await d.close();
    store.close();
  }
  const fields = noticeFields({ kind: "offline", messageId: 7, fromAgent: "s", agent: "cx", why: "", count: 1,
    since: Date.now() }, { preview: false });
  assert.match(fields.title, /^agent-relay/);
  assert.doesNotMatch(`${fields.title}${fields.subtitle}${fields.body}`, /-activate|-execute/);
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
    assert.ok(sent.json().warnings.some((w: string) => /A desktop notification was attempted on this Mac; macOS may not show it \(notifications not allowed for the app that shows them, or Focus\)\. The user can list waiting messages with doctor or by asking any session\./.test(w)), sent.text);
    const lines = readFileSync(log, "utf8").trim().split("\n");
    assert.equal(lines.length, 1);
    assert.match(lines[0], / \| secret work$/, "the preview (D89)");
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

// agent-relay notify-channel D89: what a notice shows. Preview by default; notify-preview.off restores D67's form.
const base = { messageId: 7, fromAgent: "sender", agent: "cx", why: "Codex is not running; the message waits" };

test("a notice shows who, which message and a one-line preview of at most 60 characters", () => {
  assert.equal(PREVIEW_CHARS, 60);
  assert.equal(NAME_CHARS, 40);
  assert.deepEqual(noticeFields({ ...base, body: "Please review the gate change" }, { preview: true }),
    { title: "agent-relay · sender → Codex", subtitle: "#7 · cx · Codex is not running; the message waits",
      body: "Please review the gate change" });
  const sixty = "x".repeat(60);
  assert.equal(noticeFields({ ...base, body: sixty }, { preview: true }).body, sixty, "exactly 60 is not cut");
  assert.equal(noticeFields({ ...base, body: sixty + "y" }, { preview: true }).body, sixty + "…");
  // Counted in code points, so an emoji is one character and is never split.
  assert.equal(noticeFields({ ...base, body: "😀".repeat(61) }, { preview: true }).body, "😀".repeat(60) + "…");
  assert.equal(noticeFields({ ...base, fromAgent: undefined, body: "x" }, { preview: true }).title, "agent-relay · a peer → Codex");
  assert.equal(noticeFields({ ...base, body: " \n\t " }, { preview: true }).body, "(empty message)");
});

test("control characters and line breaks become single spaces; a leading dash stays text", () => {
  const body = "  line one\r\nline\ttwo\u0000\u0007\u001b[31m\u007f\u0085\u2028\u2029end  ";
  assert.equal(noticeFields({ ...base, body }, { preview: true }).body, "line one line two [31m end");
  assert.equal(noticeFields({ ...base, body: "-execute open -a Calculator" }, { preview: true }).body,
    "-execute open -a Calculator", "the body goes on stdin, never as an argument");
});

test("names are cleaned and cut at 40 characters, and the title and subtitle never start with a dash", () => {
  const hostile = '-execute "x"\n(a,b) {k=v} ' + "n".repeat(50);
  const fields = noticeFields({ ...base, fromAgent: hostile, agent: "-cx\r\nevil", body: "hi" }, { preview: true });
  assert.equal(fields.title, `agent-relay · -execute "x" (a,b) {k=v} ${"n".repeat(15)}… → Codex`);
  assert.equal(fields.subtitle, "#7 · -cx evil · Codex is not running; the message waits");
  assert.ok(fields.title.startsWith("agent-relay · ") && fields.subtitle.startsWith("#7 · "));
  assert.doesNotMatch(fields.title + fields.subtitle, /[\u0000-\u001f]/);
});

test("notify-preview.off restores the D67 form with no message content", async () => {
  const off = noticeFields({ ...base, body: "secret body" }, { preview: false });
  assert.deepEqual(off, { title: "agent-relay", subtitle: "",
    body: '"sender" gave Codex work: message #7 to "cx" (Codex is not running; the message waits).' });

  const { dir, store, log, lines } = setup();
  writeFileSync(join(dir, "notify-preview.off"), "");
  store.send({ fromAgent: "sender", toAgent: "cx", body: "secret body" });
  const d = dispatcher(store, log, [{ state: "pending", detail: "offline", reason: "offline" }]);
  await d.flush();
  assert.equal(lines().length, 1);
  assert.doesNotMatch(lines()[0], /secret/);
  assert.match(lines()[0], /^agent-relay \|  \| "sender" gave Codex work/);
  await d.close();
  store.close();
});

test("the reason stays in the subtitle, cut at 80 characters (D89a)", () => {
  assert.equal(REASON_CHARS, 80);
  const act = "Codex has been busy for ten minutes; the message still waits in the mailbox for its next turn";
  assert.ok(Array.from(act).length > 80);
  const fields = noticeFields({ ...base, why: act, body: "work" }, { preview: true });
  assert.equal(fields.subtitle, `#7 · cx · ${Array.from(act).slice(0, 80).join("").trimEnd()}…`);
  const short = noticeFields({ ...base, why: "w", body: undefined }, { preview: true });
  assert.equal(short.subtitle, "#7 · cx");
});

// agent-relay notice-location D188: the text says which session, which project and where.
test("a notice names the session, its project and the place; without previews only the place category", () => {
  const approval = { kind: "approval" as const, messageId: 7, agent: "alice", why: "waiting for your approval in its Claude session" };
  const tab = { place: { kind: "terminal" as const, tty: "ttys003", bundle: "com.apple.Terminal", app: "Terminal" },
    session: "fix the\ngate", project: "agent-relay" };
  // notice-click-focus D190: the banner shows about 40 characters of the subtitle, so the place comes first.
  assert.equal(noticeFields({ ...approval, where: tab }, { preview: true }).subtitle,
    "Terminal ttys003 · #7 · alice · fix the gate in agent-relay");
  assert.equal(noticeFields({ ...approval, where: { place: { kind: "desktop" }, session: "你好" } }, { preview: true }).subtitle,
    "Claude desktop app · #7 · alice · 你好");
  assert.equal(noticeFields({ ...approval, where: { place: { kind: "background", id: "1a2b3c4d" }, project: "p" } },
    { preview: true }).subtitle, "background session · claude attach 1a2b3c4d · #7 · alice · p");
  assert.equal(noticeFields({ ...approval, where: { place: { kind: "unknown" } } }, { preview: true }).subtitle, "#7 · alice");
  assert.equal(noticeFields({ ...approval, where: tab }, { preview: false }).subtitle, "terminal", "no name, no tty");
  assert.equal(noticeFields({ ...approval, where: { ...tab, session: "x".repeat(80) } }, { preview: true }).subtitle,
    `Terminal ttys003 · #7 · alice · ${"x".repeat(40)}… in agent-relay`);

  const codex = { ...base, body: "hello" };
  assert.equal(noticeFields({ ...codex, where: { place: { kind: "codex-app" } } }, { preview: true }).subtitle,
    "Codex app · #7 · cx · Codex is not running; the message waits");
  assert.equal(noticeFields({ ...codex, where: { place: { kind: "codex" } } }, { preview: true }).subtitle,
    "#7 · cx · Codex is not running; the message waits", "the title already says Codex");
  assert.equal(noticeFields({ ...codex, where: { place: { kind: "codex-app" } } }, { preview: false }).subtitle, "Codex app");
});

test("a busy Codex app is named as the place; an offline Codex is not (D188)", async () => {
  const busy = setup();
  const message = busy.store.send({ fromAgent: "sender", toAgent: "cx", body: "hello" });
  busy.store.database.prepare("UPDATE wake_jobs SET created_at = ? WHERE message_id = ?")
    .run(Date.now() - BUSY_NOTIFY_AFTER_MS - 1000, message.id);
  await dispatcher(busy.store, busy.log, [{ state: "pending", detail: "Codex is working", reason: "busy" }]).flush();
  assert.match(busy.lines()[0], /\| Codex app · #\d+ · cx · Codex has been busy for ten minutes \|/);
  const offline = setup();
  offline.store.send({ fromAgent: "sender", toAgent: "cx", body: "hello" });
  await dispatcher(offline.store, offline.log, [{ state: "pending", detail: "offline", reason: "offline" }]).flush();
  assert.doesNotMatch(offline.lines()[0], /Codex app/);
});

// claude-offline-notice-fixes D194: only an explicit "offline" counts toward the Claude notice; once a notice was
// attempted, every later retry keeps saying so, without a second notice.
const ATTEMPTED = /A desktop notification was attempted on this Mac/;

test("a Claude session that is unreachable, or pending without a reason, is never told as offline", async () => {
  for (const result of [{ state: "pending", detail: "cannot be reached", reason: "unreachable" },
    { state: "pending", detail: "no reason" }] as WakeResult[]) {
    const { store, log, lines } = setup("claude");
    const message = store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
    age(store, message.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 60_000);
    const d = dispatcher(store, log, [result]);
    await d.flush();
    assert.equal(lines().length, 0, result.detail);
    assert.equal(store.wakes.forMessage(message.id)?.state, "pending");
    assert.doesNotMatch(store.wakes.forMessage(message.id)?.detail ?? "", ATTEMPTED);
    await d.close();
    store.close();
  }
});

test("after the Claude offline notice, later retries still say a notice was attempted", async () => {
  const { store, log, lines } = setup("claude");
  const message = store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
  age(store, message.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 1000);
  const d = dispatcher(store, log, []);
  await d.flush();
  assert.equal(lines().length, 1);
  for (let retry = 0; retry < 2; retry++) {
    age(store, message.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 60_000 * (retry + 2));
    await d.flush();
    assert.match(store.wakes.forMessage(message.id)?.detail ?? "", ATTEMPTED, `retry ${retry}`);
  }
  assert.equal(lines().length, 1, "still one notice");
  await d.close();
  store.close();
});

test("after a Codex notice, later retries of that message still say a notice was attempted", async () => {
  const { store, log, lines } = setup();
  const message = store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
  const d = dispatcher(store, log, [
    { state: "pending", detail: "Codex local connection unavailable", reason: "offline" },
    { state: "pending", detail: "Codex is working; ping will wait for idle", reason: "busy" },
  ]);
  await d.flush();
  assert.equal(lines().length, 1);
  store.database.prepare("UPDATE wake_jobs SET retry_at = 0 WHERE message_id = ?").run(message.id);
  await d.flush();
  const detail = store.wakes.forMessage(message.id)?.detail ?? "";
  assert.match(detail, /^Codex is working/);
  assert.match(detail, ATTEMPTED);
  assert.equal(lines().length, 1, "still one notice");
  await d.close();
  store.close();
});

test("with notices off, no retry claims a notice was attempted", async () => {
  const { store, log, lines } = setup("claude");
  const message = store.send({ fromAgent: "sender", toAgent: "cx", body: "work" });
  const d = dispatcher(store, log, [], { AGENT_RELAY_NOTIFY: "off" });
  for (let retry = 0; retry < 2; retry++) {
    age(store, message.id, CLAUDE_OFFLINE_NOTIFY_AFTER_MS + 60_000 * (retry + 1));
    await d.flush();
    assert.doesNotMatch(store.wakes.forMessage(message.id)?.detail ?? "", ATTEMPTED);
  }
  assert.equal(lines().length, 0);
  await d.close();
  store.close();
});
