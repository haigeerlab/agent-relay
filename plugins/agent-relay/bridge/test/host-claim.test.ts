// agent-relay acceptance-030-gaps D75/D75a: a Codex task names its host without binding wake; the claim grants nothing.
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { session } from "./support/session.js";

const CLAIM = { app: "codex", sessionId: "thread-a" };

function mailbox() {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-host-claim-"));
  const log = join(dir, "notices.log");
  return { dir, log, env: { AGENT_RELAY_NOTIFY: "", AGENT_RELAY_NOTIFY_LOG: log } };
}

test("a host claim records the Codex host and binds nothing", async () => {
  const { dir, log, env } = mailbox();
  const codex = await session(dir, null, env);
  const claude = await session(dir, "claude-sender", env);
  try {
    const registered = await codex.call("bridge_register", { agent: "cx", wake: null, host: CLAIM });
    assert.ok(registered.ok, registered.text);
    assert.equal(registered.json().wake, null);
    const store = new BridgeStore(join(dir, "bridge.sqlite"));
    assert.deepEqual(store.getAgent("cx")?.host, CLAIM);
    assert.equal(store.wakes.target("cx"), null);
    store.close();

    assert.ok((await claude.call("bridge_register", { agent: "sender" })).ok);
    const sent = await claude.call("bridge_send", { from: "sender", to: "cx", body: "work" });
    assert.ok(sent.ok, sent.text);
    assert.equal(sent.json().wake, null, "no ping");
    assert.ok(sent.json().warnings.some((w: string) => /is a Codex session without a wake binding/.test(w)), sent.text);
    assert.ok(!sent.json().warnings.some((w: string) => /no known host/.test(w)), "the host is known now");
    // agent-relay acceptance-030-gaps D76: a notice is only attempted; macOS may drop it.
    assert.ok(sent.json().warnings.some((w: string) => /notification was attempted/.test(w)), sent.text);
    assert.ok(!sent.json().warnings.some((w: string) => /The user was notified/.test(w)), "never claims the user saw it");
    assert.equal(readFileSync(log, "utf8").trim().split("\n").length, 1, "the D67 notice is attempted");

    const agents = (await claude.call("bridge_agents", {})).json().agents;
    assert.equal(agents.find((a: any) => a.name === "cx").host.verified, false, "a claim is not verified");
    assert.equal(agents.find((a: any) => a.name === "sender").host.verified, true, "a Claude session is verified");
  } finally {
    await Promise.all([codex.close(), claude.close()]);
  }
});

test("a host claim is refused from a Claude session, for another app, or beside a different wake target", async () => {
  const { dir, env } = mailbox();
  const codex = await session(dir, null, env);
  const claude = await session(dir, "claude-self", env);
  try {
    const fromClaude = await claude.call("bridge_register", { agent: "c1", wake: null, host: CLAIM });
    assert.equal(fromClaude.ok, false);
    assert.match(fromClaude.text, /verified/);
    const otherApp = await codex.call("bridge_register", { agent: "c2", wake: null, host: { app: "claude", sessionId: "x" } });
    assert.equal(otherApp.ok, false);
    const differing = await codex.call("bridge_register",
      { agent: "c3", wake: { app: "codex", sessionId: "thread-b" }, host: CLAIM });
    assert.equal(differing.ok, false);
    assert.match(differing.text, /differ/);
    const same = await codex.call("bridge_register", { agent: "c4", wake: { app: "codex", sessionId: "thread-a" }, host: CLAIM });
    assert.ok(same.ok, same.text);
  } finally {
    await Promise.all([codex.close(), claude.close()]);
  }
});

test("a claimed host grants nothing: no takeover, no wake for another thread, no sending without registering (D75a)", async () => {
  const { dir, env } = mailbox();
  const first = await session(dir, null, env);
  const second = await session(dir, null, env);
  try {
    assert.ok((await first.call("bridge_register", { agent: "cx", wake: null, host: CLAIM })).ok);
    // Another Codex process naming another thread, by wake or by host, needs takeover like any other owner conflict.
    for (const args of [{ wake: { app: "codex", sessionId: "thread-b" } }, { wake: null, host: { app: "codex", sessionId: "thread-b" } }]) {
      const refused = await second.call("bridge_register", { agent: "cx", ...args });
      assert.equal(refused.ok, false, JSON.stringify(args));
      assert.match(refused.text, /registered by another codex session/);
    }
    // Naming no thread at all gets the hint, which names host as well as wake.
    const unnamed = await second.call("bridge_register", { agent: "cx", wake: null });
    assert.equal(unnamed.ok, false);
    assert.match(unnamed.text, /or, without pings, host: \{app: "codex"/);
    const store = new BridgeStore(join(dir, "bridge.sqlite"));
    assert.equal(store.wakes.target("cx"), null, "no binding was created by any of it");
    store.register("peer");
    store.close();
    // The claim does not prove the name to a process that did not register it.
    const impersonated = await second.call("bridge_send", { from: "cx", to: "peer", body: "x" });
    assert.equal(impersonated.ok, false);
    assert.match(impersonated.text, /not an identity of this session/);
    assert.ok((await first.call("bridge_send", { from: "cx", to: "peer", body: "x" })).ok, "the registering process can");
  } finally {
    await Promise.all([first.close(), second.close()]);
  }
  assert.ok(!existsSync(join(dir, "notified")), "nothing notified here");
});
