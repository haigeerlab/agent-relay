// agent-relay identity-check: a name belongs to the host session that registered it.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { session } from "./support/session.js";

test("a send or acknowledgement is accepted only from the session that owns the name", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-"));
  const a = await session(dir, "claude-session-a");
  const b = await session(dir, "claude-session-b");
  const codex = await session(dir, null);
  try {
    assert.ok((await a.call("bridge_register", { agent: "alice" })).ok);
    assert.ok((await b.call("bridge_register", { agent: "bob" })).ok);
    assert.ok((await codex.call("bridge_register", { agent: "carol" })).ok);
    assert.equal((await a.call("bridge_agents", {})).json().agents.find((x: any) => x.name === "alice").host.sessionId,
      "claude-session-a");

    const sent = await a.call("bridge_send", { from: "alice", to: "bob", body: "hello" });
    assert.ok(sent.ok, sent.text);
    assert.ok((await codex.call("bridge_send", { from: "carol", to: "bob", body: "hi" })).ok);

    const forged = await a.call("bridge_send", { from: "bob", to: "carol", body: "as bob" });
    assert.equal(forged.ok, false);
    assert.match(forged.text, /"bob" is not an identity of this session/);
    assert.match(forged.text, /bridge_register/);
    assert.match(forged.text, /never guess/i);
    const ghost = await codex.call("bridge_send", { from: "ghost", to: "bob", body: "?" });
    assert.equal(ghost.ok, false);
    assert.match(ghost.text, /"ghost" is not registered/);

    const id = sent.json().id;
    assert.equal((await a.call("bridge_ack", { agent: "bob", ids: [id] })).ok, false, "ack as another session's name");
    assert.equal((await a.call("bridge_wait", { agent: "bob", timeoutSeconds: 1 })).ok, false, "wait acknowledges by default");
    assert.ok((await a.call("bridge_wait", { agent: "bob", timeoutSeconds: 1, acknowledge: false })).ok, "reading is not checked");
    assert.ok((await b.call("bridge_ack", { agent: "bob", ids: [id] })).ok);
  } finally {
    await Promise.all([a.close(), b.close(), codex.close()]);
  }
});

test("a Claude session keeps its names across a bridge restart; a Codex session registers again", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-restart-"));
  let a = await session(dir, "claude-session-a");
  let codex = await session(dir, null);
  await a.call("bridge_register", { agent: "alice" });
  await codex.call("bridge_register", { agent: "carol" });
  await Promise.all([a.close(), codex.close()]);

  a = await session(dir, "claude-session-a");
  codex = await session(dir, null);
  try {
    assert.ok((await a.call("bridge_send", { from: "alice", to: "carol", body: "still me" })).ok);
    const before = await codex.call("bridge_send", { from: "carol", to: "alice", body: "me too" });
    assert.equal(before.ok, false);
    assert.match(before.text, /bridge_register/);
    assert.ok((await codex.call("bridge_register", { agent: "carol" })).ok);
    assert.ok((await codex.call("bridge_send", { from: "carol", to: "alice", body: "me too" })).ok);
  } finally {
    await Promise.all([a.close(), codex.close()]);
  }
});

// agent-relay identity-check: takeover (assumption 4).
test("another session's name is not taken over without takeover: true; with it, the old session loses the name", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-takeover-"));
  const a = await session(dir, "claude-session-a");
  const b = await session(dir, "claude-session-b");
  const codex = await session(dir, null);
  try {
    assert.ok((await a.call("bridge_register", { agent: "alice" })).ok);
    assert.ok((await a.call("bridge_register", { agent: "alice", capabilities: ["review"] })).ok, "same session again");

    const taken = await b.call("bridge_register", { agent: "alice" });
    assert.equal(taken.ok, false);
    assert.match(taken.text, /"alice" is registered by another claude session \(no longer running\)/);
    assert.match(taken.text, /takeover: true/);
    const byCodex = await codex.call("bridge_register", { agent: "alice" });
    assert.equal(byCodex.ok, false, "an unknown caller cannot claim an owned name either");

    const moved = await b.call("bridge_register", { agent: "alice", takeover: true });
    assert.ok(moved.ok, moved.text);
    assert.equal(moved.json().host.sessionId, "claude-session-b");
    assert.ok((await b.call("bridge_send", { from: "alice", to: "alice", body: "mine now" })).ok);
    const old = await a.call("bridge_send", { from: "alice", to: "alice", body: "still mine?" });
    assert.equal(old.ok, false, "the recorded host decides for a Claude caller");
  } finally {
    await Promise.all([a.close(), b.close(), codex.close()]);
  }
});

test("a name with no recorded owner is claimed by its next registration", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-claim-"));
  const codex = await session(dir, null);
  const b = await session(dir, "claude-session-b");
  try {
    assert.equal((await codex.call("bridge_register", { agent: "shared" })).json().host, null);
    const claimed = await b.call("bridge_register", { agent: "shared" });
    assert.ok(claimed.ok, claimed.text);
    assert.equal(claimed.json().host.sessionId, "claude-session-b");
  } finally {
    await Promise.all([codex.close(), b.close()]);
  }
});

test("a Codex session re-registers a bound name by claiming the same thread", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-codex-"));
  const fixture = join(dir, "codex-home");
  mkdirSync(fixture);
  writeFileSync(join(fixture, "config.toml"), 'approval_policy = "on-request"\n');
  const env = { CODEX_HOME: fixture };
  let codex = await session(dir, null, env);
  assert.ok((await codex.call("bridge_register", { agent: "carol", wake: { app: "codex", sessionId: "thread-1" } })).ok);
  await codex.close();
  codex = await session(dir, null, env);
  try {
    const bare = await codex.call("bridge_register", { agent: "carol" });
    assert.equal(bare.ok, false);
    assert.match(bare.text, /wake: \{app: "codex", sessionId/);
    assert.equal((await codex.call("bridge_register", { agent: "carol", wake: { app: "codex", sessionId: "thread-2" } })).ok, false);
    assert.ok((await codex.call("bridge_register", { agent: "carol", wake: { app: "codex", sessionId: "thread-1" } })).ok);
  } finally {
    await codex.close();
  }
});

test("a Claude session binds wake only to itself", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-bind-"));
  const a = await session(dir, "claude-session-a");
  try {
    for (const wake of [{ app: "claude", sessionId: "claude-session-x" }, { app: "codex", sessionId: "thread-1" }]) {
      const other = await a.call("bridge_register", { agent: "alice", wake });
      assert.equal(other.ok, false, JSON.stringify(wake));
      assert.match(other.text, /only to this session/);
    }
    assert.ok((await a.call("bridge_register", { agent: "alice", wake: { app: "claude", sessionId: "claude-session-a" } })).ok);
    assert.deepEqual((await a.call("bridge_register", { agent: "alice", wake: "auto" })).json().wake,
      { app: "claude", sessionId: "claude-session-a" });
  } finally {
    await a.close();
  }
});
