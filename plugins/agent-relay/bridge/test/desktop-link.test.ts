import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { session } from "./support/session.js";

const LINK = "claude://claude.ai/epitaxy/local_00000000-0000-4000-8000-000000000001";

test("a verified Claude caller records, keeps, cleans, and clears its desktop link", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-desktop-link-"));
  const claude = await session(dir, "claude-a");
  try {
    const registered = await claude.call("bridge_register", { agent: "alice", desktop: { link: LINK, title: `  hello\u0000   ${"x".repeat(300)}  ` } });
    assert.ok(registered.ok, registered.text);
    let store = new BridgeStore(join(dir, "bridge.sqlite"));
    assert.deepEqual(store.getAgent("alice")?.desktop, { link: LINK, title: `hello ${"x".repeat(114)}` });
    store.close();
    assert.ok((await claude.call("bridge_register", { agent: "alice" })).ok, "omitted keeps desktop");
    assert.ok((await claude.call("bridge_register", { agent: "alice", desktop: null })).ok, "null clears desktop");
    store = new BridgeStore(join(dir, "bridge.sqlite"));
    assert.equal(store.getAgent("alice")?.desktop, null);
    store.close();
  } finally { await claude.close(); }
});

test("desktop link titles are truncated by code point", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-desktop-title-"));
  const claude = await session(dir, "claude-a");
  try {
    assert.ok((await claude.call("bridge_register", { agent: "alice", desktop: { link: LINK, title: "😀".repeat(130) } })).ok);
    const store = new BridgeStore(join(dir, "bridge.sqlite"));
    const title = store.getAgent("alice")?.desktop?.title;
    assert.equal(Array.from(title ?? []).length, 120);
    assert.equal(title, "😀".repeat(120));
    store.close();
  } finally { await claude.close(); }
});

test("takeover and wake rebind clear or replace a stale desktop link", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-desktop-takeover-"));
  const a = await session(dir, "claude-a");
  const b = await session(dir, "claude-b");
  const linkB = "claude://claude.ai/epitaxy/local_00000000-0000-4000-8000-000000000002";
  try {
    assert.ok((await a.call("bridge_register", { agent: "alice", desktop: { link: LINK } })).ok);
    assert.ok((await b.call("bridge_register", { agent: "alice", takeover: true })).ok);
    let store = new BridgeStore(join(dir, "bridge.sqlite"));
    assert.equal(store.getAgent("alice")?.desktop, null, "takeover without desktop clears it");
    store.close();
    assert.ok((await a.call("bridge_register", { agent: "alice", takeover: true, desktop: { link: LINK } })).ok);
    assert.ok((await b.call("bridge_register", { agent: "alice", takeover: true, desktop: { link: linkB } })).ok);
    store = new BridgeStore(join(dir, "bridge.sqlite"));
    assert.deepEqual(store.getAgent("alice")?.desktop, { link: linkB });
    store.close();
    assert.ok((await a.call("bridge_register", { agent: "alice", takeover: true, wake: "auto", desktop: { link: LINK } })).ok);
    assert.ok((await b.call("bridge_register", { agent: "alice", takeover: true, wake: "auto" })).ok);
    store = new BridgeStore(join(dir, "bridge.sqlite"));
    assert.equal(store.getAgent("alice")?.desktop, null, "wake rebind without desktop clears it");
    store.close();
    assert.ok((await a.call("bridge_register", { agent: "alice", takeover: true, wake: "auto", desktop: { link: LINK } })).ok);
    assert.ok((await b.call("bridge_register", { agent: "alice", takeover: true, wake: "auto", desktop: { link: linkB } })).ok);
    store = new BridgeStore(join(dir, "bridge.sqlite"));
    assert.deepEqual(store.getAgent("alice")?.desktop, { link: linkB }, "wake rebind replaces it when supplied");
    store.close();
  } finally { await Promise.all([a.close(), b.close()]); }
});

test("desktop links require a verified Claude caller and D287 link format", async () => {
  // Script identities are CLI-only: they cannot call bridge_register over MCP, and
  // register-script-identity reaches BridgeStore.register without a desktop argument.
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-desktop-refuse-"));
  const claude = await session(dir, "claude-a");
  const codex = await session(dir, null);
  try {
    const invalid = await claude.call("bridge_register", { agent: "alice", desktop: { link: "https://example.test" } });
    assert.equal(invalid.ok, false);
    assert.match(invalid.text, /desktop link/i);
    for (const caller of [codex]) {
      const refused = await caller.call("bridge_register", { agent: "bob", host: { app: "codex", sessionId: "thread-a" }, desktop: { link: LINK } });
      assert.equal(refused.ok, false);
      assert.match(refused.text, /Claude desktop sessions/);
    }
    const unverified = await codex.call("bridge_register", { agent: "unverified", desktop: { link: LINK } });
    assert.equal(unverified.ok, false);
    assert.match(unverified.text, /Claude desktop sessions/);
  } finally { await Promise.all([claude.close(), codex.close()]); }
});
