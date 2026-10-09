// agent-relay identity-check: a name belongs to the host session that registered it.
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { retireAgent } from "../src/lifecycle.js";
import { session } from "./support/session.js";

/** Retire as the CLI `retire` does (orchestrator-removal D91: no MCP tool); returns when it was retired. */
function retire(dir: string, agent: string, by: string): string {
  const store = new BridgeStore(join(dir, "bridge.sqlite"));
  try {
    retireAgent(store, agent, { by, note: "done" });
    return store.getAgent(agent)!.retiredAt!;
  } finally {
    store.close();
  }
}

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

// agent-relay takeover-wake-rebind D186: takeover with a new wake replaces another session's binding.
test("takeover: true with a new wake replaces another session's wake binding and cancels its pending pings", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-rebind-"));
  const a = await session(dir, "claude-session-a");
  const b = await session(dir, "claude-session-b");
  const c = await session(dir, "claude-session-c");
  const codex = await session(dir, null);
  const jobs = (agent: string) => {
    const store = new BridgeStore(join(dir, "bridge.sqlite"));
    try {
      return store.wakes.list(agent).map((job) => ({ state: job.state, sessionId: job.target.sessionId }));
    } finally {
      store.close();
    }
  };
  try {
    const bound = { app: "claude", sessionId: "claude-session-a" };
    assert.deepEqual((await a.call("bridge_register", { agent: "alice", wake: "auto" })).json().wake, bound);
    assert.deepEqual((await a.call("bridge_register", { agent: "alice", wake: "auto" })).json().wake, bound, "same session again");
    assert.ok((await codex.call("bridge_register", { agent: "carol" })).ok);
    assert.ok((await codex.call("bridge_send", { from: "carol", to: "alice", body: "while a was bound" })).ok);
    assert.deepEqual(jobs("alice"), [{ state: "pending", sessionId: "claude-session-a" }]);

    const refused = await b.call("bridge_register", { agent: "alice", wake: "auto" });
    assert.equal(refused.ok, false);
    assert.match(refused.text, /takeover: true/);
    const kept = await b.call("bridge_register", { agent: "bob" });
    assert.ok(kept.ok, kept.text);
    assert.deepEqual(jobs("alice"), [{ state: "pending", sessionId: "claude-session-a" }], "a refusal changes nothing");

    const moved = await b.call("bridge_register", { agent: "alice", takeover: true, wake: "auto" });
    assert.ok(moved.ok, moved.text);
    assert.deepEqual(moved.json().wake, { app: "claude", sessionId: "claude-session-b" });
    assert.equal(moved.json().host.sessionId, "claude-session-b");
    assert.match(moved.json().notes.join(" "), /taken over/);
    assert.equal(moved.json().unread, 1, "the message waits in the inbox");
    assert.deepEqual(jobs("alice"), [{ state: "cancelled", sessionId: "claude-session-a" }]);

    const explicit = await c.call("bridge_register",
      { agent: "alice", takeover: true, wake: { app: "claude", sessionId: "claude-session-c" } });
    assert.ok(explicit.ok, explicit.text);
    assert.deepEqual(explicit.json().wake, { app: "claude", sessionId: "claude-session-c" });

    const noWake = await b.call("bridge_register", { agent: "alice", takeover: true });
    assert.ok(noWake.ok, noWake.text);
    assert.deepEqual(noWake.json().wake, { app: "claude", sessionId: "claude-session-c" }, "omitted wake keeps the binding");
  } finally {
    await Promise.all([a.close(), b.close(), c.close(), codex.close()]);
  }
});

// agent-relay ops-commands: whoami (assumption 3).
test("bridge_sessions.whoami lists this session's host, project and identities", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-whoami-"));
  let a = await session(dir, "claude-session-a", { CLAUDE_PROJECT_DIR: "/work/my-project" });
  const b = await session(dir, "claude-session-b");
  const codex = await session(dir, null);
  try {
    await a.call("bridge_register", { agent: "alice" });
    await b.call("bridge_register", { agent: "bob" });
    await codex.call("bridge_register", { agent: "carol" });
    const mine = (await a.call("bridge_sessions", {})).json().whoami;
    assert.deepEqual(mine.host, { app: "claude", sessionId: "claude-session-a", verified: true });
    assert.equal(mine.project, "my-project");
    assert.equal(mine.sessionName, null, "no live Claude registry entry in this test");
    assert.deepEqual(mine.identities.map((x: any) => [x.name, x.provenHere]), [["alice", true]]);
    assert.deepEqual(mine.identities[0].recordedHost, { app: "claude", sessionId: "claude-session-a", verified: true });
    assert.equal(mine.identities[0].wake, null);

    const theirs = (await codex.call("bridge_sessions", {})).json().whoami;
    assert.equal(theirs.host, null);
    assert.equal(theirs.project, null);
    assert.deepEqual(theirs.identities.map((x: any) => x.name), ["carol"]);
    assert.match(theirs.note, /Codex/);

    await a.close();
    a = await session(dir, "claude-session-a", { CLAUDE_PROJECT_DIR: "/work/my-project" });
    assert.deepEqual((await a.call("bridge_sessions", {})).json().whoami.identities.map((x: any) => [x.name, x.provenHere]),
      [["alice", false]], "recorded for this session, not yet registered in this process");
  } finally {
    await Promise.all([a.close(), b.close(), codex.close()]);
  }
});

// agent-relay cleanup-gaps D61: a retired name comes back only with reactivate: true.
test("a retired name is refused, even with takeover, until reactivate: true; the result says it was reactivated", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-reactivate-"));
  const a = await session(dir, "claude-session-a");
  const b = await session(dir, "claude-session-b");
  try {
    assert.ok((await a.call("bridge_register", { agent: "alice" })).ok);
    const retiredAt = retire(dir, "alice", "alice");

    for (const [who, args] of [[a, {}], [b, { takeover: true }], [a, { wake: null }]] as const) {
      const refused = await who.call("bridge_register", { agent: "alice", ...args });
      assert.equal(refused.ok, false, JSON.stringify(args));
      assert.match(refused.text, /"alice" was retired at /);
      assert.match(refused.text, /reactivate: true/);
    }
    const agents = (await a.call("bridge_agents", { includeRetired: true })).json().agents;
    assert.equal(agents.find((x: any) => x.name === "alice").retiredAt, retiredAt, "a refusal changes nothing");

    const back = await a.call("bridge_register", { agent: "alice", reactivate: true });
    assert.ok(back.ok, back.text);
    assert.equal(back.json().reactivated, true);
    assert.equal(back.json().retiredAt, null);
    assert.ok(back.json().notes.some((note: string) => note.includes(retiredAt)), back.text);

    const again = await a.call("bridge_register", { agent: "alice", reactivate: true });
    assert.ok(again.ok, again.text);
    assert.equal(again.json().reactivated, undefined, "an active name is a normal registration");
  } finally {
    await Promise.all([a.close(), b.close()]);
  }
});

// agent-relay register-retired-hint D64: an ownership refusal of a retired name says it is retired.
test("another session's reactivate on a retired name is refused for ownership and names the retirement", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-identity-retired-hint-"));
  const a = await session(dir, "claude-session-a");
  const b = await session(dir, "claude-session-b");
  try {
    assert.ok((await a.call("bridge_register", { agent: "busy" })).ok);
    const active = await b.call("bridge_register", { agent: "busy" });
    assert.equal(active.ok, false);
    assert.match(active.text, /registered by another claude session/);
    assert.doesNotMatch(active.text, /retired/, "an active name's refusal is unchanged");

    assert.ok((await a.call("bridge_register", { agent: "gone" })).ok);
    const retiredAt = retire(dir, "gone", "gone");
    const refused = await b.call("bridge_register", { agent: "gone", reactivate: true });
    assert.equal(refused.ok, false);
    assert.match(refused.text, /registered by another claude session/);
    assert.ok(refused.text.includes(`It was retired at ${retiredAt} by gone`), refused.text);
    assert.match(refused.text, /reactivate: true together with takeover: true/);
    const row = (await a.call("bridge_agents", { includeRetired: true })).json().agents.find((x: any) => x.name === "gone");
    assert.equal(row.retiredAt, retiredAt, "the refusal changes nothing");

    const back = await b.call("bridge_register", { agent: "gone", reactivate: true, takeover: true });
    assert.ok(back.ok, back.text);
    assert.equal(back.json().reactivated, true);
  } finally {
    await Promise.all([a.close(), b.close()]);
  }
});
