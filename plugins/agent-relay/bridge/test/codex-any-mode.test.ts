// agent-relay wake-any-mode D140, D141: a Codex wake is sent in every approval mode, with no gate before or after it.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { WakeDispatcher } from "../src/wake-dispatcher.js";
import type { WakeJob, WakeResult } from "../src/wake-queue.js";
import { session } from "./support/session.js";

function setup() {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-any-mode-"));
  const codexHome = join(dir, "codex");
  mkdirSync(codexHome);
  writeFileSync(join(codexHome, "config.toml"), 'approvals_reviewer = "guardian_subagent"\n');
  const store = new BridgeStore(join(dir, "bridge.sqlite"));
  store.register("s");
  store.register("cx");
  store.wakes.bind("cx", { app: "codex", sessionId: "thread-cx" });
  const log = join(dir, "notices.log");
  return { dir, store, log, env: { CODEX_HOME: codexHome, AGENT_RELAY_NOTIFY_LOG: log } };
}

function fakeWake(calls: string[]) {
  return async (job: WakeJob): Promise<WakeResult> => {
    calls.push(job.target.sessionId);
    return { state: "accepted", detail: "Codex confirmed a new turn" };
  };
}

test("an auto-approved Codex session is woken once, with nothing checked afterwards", async () => {
  const { dir, store, log, env } = setup();
  const calls: string[] = [];
  const message = store.send({ fromAgent: "s", toAgent: "cx", body: "work" });
  const d = new WakeDispatcher(store, { env, codexWake: fakeWake(calls) });
  await d.flush();
  assert.deepEqual(calls, ["thread-cx"]);
  const job = store.wakes.forMessage(message.id);
  assert.equal(job?.state, "accepted");
  assert.equal(job?.detail, "Codex confirmed a new turn");
  assert.equal(existsSync(log), false, "no notice for a delivered wake");
  assert.equal(existsSync(join(dir, "codex-gate.off")), false);
  await d.close();
  store.close();
});

test("a codex-gate.off left by an older bridge neither holds a wake nor is touched", async () => {
  const { dir, store, env } = setup();
  const off = join(dir, "codex-gate.off");
  writeFileSync(off, "turn t of thread-cx: missing\n");
  const calls: string[] = [];
  const message = store.send({ fromAgent: "s", toAgent: "cx", body: "work" });
  const d = new WakeDispatcher(store, { env, codexWake: fakeWake(calls) });
  await d.flush();
  assert.deepEqual(calls, ["thread-cx"]);
  assert.equal(store.wakes.forMessage(message.id)?.state, "accepted");
  assert.ok(existsSync(off), "never deleted by agent-relay");
  assert.equal(readdirSync(dir).includes("notified"), false, "no gate-off notice");
  await d.close();
  store.close();
});

test("an auto-approved Codex session binds wake", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-any-mode-register-"));
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
});
