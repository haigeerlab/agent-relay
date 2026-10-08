// agent-relay codex-gated-wake D66: a gated Codex wake is sent only where the gate is known to work, and checked after.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { type CodexGate, defaultCodexGate, GATE_OFF_FILE, type TurnContext, verifyTurn, versionAtLeast } from "../src/codex-gate.js";
import { sweepDeliveryFailures } from "../src/notices.js";
import { WakeDispatcher } from "../src/wake-dispatcher.js";
import type { WakeJob, WakeResult } from "../src/wake-queue.js";
import { session } from "./support/session.js";

const GATED: TurnContext = { approvalsReviewer: "user", approvalPolicy: "on-request", sandbox: "read-only" };
const instant = { intervalMs: 500, timeoutMs: 10_000, sleep: async () => {} };

test("the version threshold is numeric and unreadable versions are not new enough", () => {
  assert.equal(versionAtLeast("26.930.61225"), true);
  assert.equal(versionAtLeast("26.930"), true);
  assert.equal(versionAtLeast("27.1"), true);
  assert.equal(versionAtLeast("26.929.9"), false);
  assert.equal(versionAtLeast("26.93"), false);
  assert.equal(versionAtLeast(null), false);
  assert.equal(versionAtLeast("beta"), false);
});

test("the after-turn check waits for a late record, and fails only after the whole window", async () => {
  let reads = 0;
  const late: CodexGate = { appVersion: () => "26.930", turnContext: () => (++reads >= 3 ? GATED : null) };
  assert.equal(await verifyTurn(late, "t", "turn", instant), "ok");
  assert.equal(reads, 3);

  let slept = 0;
  const never: CodexGate = { appVersion: () => "26.930", turnContext: () => null };
  assert.equal(await verifyTurn(never, "t", "turn", { ...instant, sleep: async (ms) => { slept += ms; } }), "missing");
  assert.equal(slept, 10_000, "0.5 s steps for the full 10 s");

  const ungated: CodexGate = { appVersion: () => "26.930",
    turnContext: () => ({ approvalsReviewer: "auto_review", approvalPolicy: "on-request", sandbox: "workspace-write" }) };
  assert.equal(await verifyTurn(ungated, "t", "turn", instant), "mismatch");
});

test("the rollout is found by the exact thread id and the exact turn", () => {
  const home = mkdtempSync(join(tmpdir(), "agent-relay-gate-home-"));
  const day = join(home, "sessions", "2026", "10", "08");
  mkdirSync(day, { recursive: true });
  const line = (turn: string, reviewer: string, sandbox: string) => JSON.stringify({ type: "turn_context",
    payload: { turn_id: turn, approval_policy: "on-request", approvals_reviewer: reviewer, sandbox_policy: { type: sandbox } } });
  writeFileSync(join(day, "rollout-2026-10-08T10-00-00-thread-a.jsonl"),
    [line("turn-1", "auto_review", "workspace-write"), line("turn-2", "user", "read-only")].join("\n") + "\n");
  writeFileSync(join(day, "rollout-2026-10-08T11-00-00-other-thread-a.jsonl"), line("turn-2", "auto_review", "workspace-write") + "\n");
  const gate = defaultCodexGate({ CODEX_HOME: home });
  assert.deepEqual(gate.turnContext("thread-a", "turn-2"), GATED);
  assert.deepEqual(gate.turnContext("thread-a", "turn-1"), { approvalsReviewer: "auto_review", approvalPolicy: "on-request", sandbox: "workspace-write" });
  assert.equal(gate.turnContext("thread-a", "turn-9"), null);
  assert.equal(gate.turnContext("thread-b", "turn-2"), null);
});

function setup(autoApproved = true) {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-gate-"));
  const codexHome = join(dir, "codex");
  mkdirSync(codexHome);
  writeFileSync(join(codexHome, "config.toml"), autoApproved ? 'approvals_reviewer = "guardian_subagent"\n' : "");
  const store = new BridgeStore(join(dir, "bridge.sqlite"));
  store.register("s");
  store.register("cx");
  store.wakes.bind("cx", { app: "codex", sessionId: "thread-cx" });
  const log = join(dir, "notices.log");
  return { dir, store, log, env: { CODEX_HOME: codexHome, AGENT_RELAY_NOTIFY_LOG: log } };
}

function fakeWake(calls: string[], turnId = "turn-x") {
  return async (job: WakeJob, ready: () => string | null): Promise<WakeResult> => {
    const reason = ready();
    if (reason) { calls.push("held"); return { state: "held", detail: reason }; }
    calls.push(job.target.sessionId);
    return { state: "accepted", detail: "Codex confirmed a new turn", turnId };
  };
}

test("auto-approval no longer holds a ping: it is woken gated and checked", async () => {
  const { store, env } = setup();
  const calls: string[] = [];
  const asked: string[] = [];
  const message = store.send({ fromAgent: "s", toAgent: "cx", body: "work" });
  const d = new WakeDispatcher(store, { env, codexWake: fakeWake(calls), verify: instant,
    gate: { appVersion: () => "26.930.61225", turnContext: (t, turn) => { asked.push(`${t}/${turn}`); return GATED; } } });
  await d.flush();
  assert.deepEqual(calls, ["thread-cx"]);
  assert.deepEqual(asked, ["thread-cx/turn-x"]);
  assert.equal(store.wakes.forMessage(message.id)?.state, "accepted");
  await d.close();
  store.close();
});

test("an old or unreadable app version holds the ping", async () => {
  for (const version of ["26.929", null]) {
    const { store, env } = setup();
    const calls: string[] = [];
    const message = store.send({ fromAgent: "s", toAgent: "cx", body: "work" });
    const d = new WakeDispatcher(store, { env, codexWake: fakeWake(calls), verify: instant,
      gate: { appVersion: () => version, turnContext: () => GATED } });
    await d.flush();
    assert.deepEqual(calls, ["held"]);
    const job = store.wakes.forMessage(message.id);
    assert.equal(job?.state, "held");
    assert.match(job?.detail ?? "", /26\.930 or later/);
    await d.close();
    store.close();
  }
});

test("a turn whose record does not show the gate turns gated wake off, notifies once, and holds later pings", async () => {
  for (const context of [null, { approvalsReviewer: "auto_review", approvalPolicy: "on-request", sandbox: "workspace-write" }]) {
    const { dir, store, log, env } = setup(false);
    const calls: string[] = [];
    store.send({ fromAgent: "s", toAgent: "cx", body: "first" });
    const d = new WakeDispatcher(store, { env, codexWake: fakeWake(calls), verify: instant,
      gate: { appVersion: () => "26.930", turnContext: () => context } });
    await d.flush();
    assert.ok(existsSync(join(dir, GATE_OFF_FILE)), "gate off");
    assert.equal(readFileSync(log, "utf8").trim().split("\n").length, 1);
    assert.match(readFileSync(log, "utf8"), /gated Codex wake is off/);
    store.wakes.finish(store.wakes.forMessage(1)!, { state: "accepted", detail: "seen" });
    const second = store.send({ fromAgent: "s", toAgent: "cx", body: "second" });
    store.database.prepare("UPDATE wake_jobs SET state = 'acknowledged' WHERE message_id = 1").run();
    await d.flush();
    assert.deepEqual(calls, ["thread-cx"], "no second wake");
    const held = store.wakes.forMessage(second.id);
    assert.equal(held?.state, "held");
    assert.match(held?.detail ?? "", /codex-gate\.off/);
    await d.close();
    store.close();
  }
});

test("an auto-approved Codex session binds wake; a held ping tells the sender why", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-gate-register-"));
  const codexHome = join(dir, "codex-home");
  mkdirSync(codexHome);
  writeFileSync(join(codexHome, "config.toml"), 'approvals_reviewer = "guardian_subagent"\n');
  const codex = await session(dir, null, { CODEX_HOME: codexHome });
  try {
    const bound = await codex.call("bridge_register", { agent: "cx", wake: { app: "codex", sessionId: "thread-cx" } });
    assert.ok(bound.ok, bound.text);
    assert.deepEqual(bound.json().wake, { app: "codex", sessionId: "thread-cx" });
  } finally {
    await codex.close();
  }
  const { store, env } = setup();
  store.send({ fromAgent: "s", toAgent: "cx", body: "work" });
  const d = new WakeDispatcher(store, { env, codexWake: fakeWake([]), verify: instant,
    gate: { appVersion: () => null, turnContext: () => GATED } });
  await d.flush();
  assert.equal(sweepDeliveryFailures(store), 1);
  assert.match(store.inbox("s").find((m) => m.fromAgent === "bridge")?.body ?? "", /gated Codex wake could not be confirmed safe/);
  await d.close();
  store.close();
});
