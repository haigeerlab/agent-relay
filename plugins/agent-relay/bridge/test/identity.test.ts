// agent-relay identity-check: a name belongs to the host session that registered it.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
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
