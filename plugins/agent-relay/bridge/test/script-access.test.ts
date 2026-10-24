// agent-relay script-access (D240–D245): scripts read the mailbox read-only and send as a script identity.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";

function mailbox(): string {
  const dir = mkdtempSync(join(tmpdir(), "ar-script-"));
  return join(dir, "bridge.sqlite");
}

// D242: a read-only store never writes, never migrates and never sweeps.
test("a read-only store refuses writes (D242)", () => {
  const path = mailbox();
  const writer = new BridgeStore(path);
  writer.register("asker");
  writer.close();
  const reader = new BridgeStore(path, { readOnly: true });
  assert.equal(reader.readOnly, true);
  assert.equal(reader.agents().length, 1);
  assert.throws(() => reader.register("other"), /readonly|read-only/i);
  reader.close();
});

test("a read-only store does not migrate an older mailbox (D242)", () => {
  const path = mailbox();
  const writer = new BridgeStore(path);
  writer.close();
  const raw = new DatabaseSync(path);
  raw.exec("PRAGMA user_version = 6");
  raw.close();
  assert.throws(() => new BridgeStore(path, { readOnly: true }), /schema 6.*schema 7|upgrade/i);
  const check = new DatabaseSync(path, { readOnly: true });
  assert.equal((check.prepare("PRAGMA user_version").get() as { user_version: number }).user_version, 6);
  check.close();
});

test("a read-only store does not expire an overdue message (D242)", () => {
  const path = mailbox();
  const writer = new BridgeStore(path);
  for (const name of ["asker", "helper"]) writer.register(name);
  const message = writer.send({ fromAgent: "asker", toAgent: "helper", body: "q", expiresInSeconds: 60 });
  const raw = (writer as unknown as { db: DatabaseSync }).db;
  raw.prepare("UPDATE messages SET expires_at = ? WHERE id = ?").run(Date.now() - 1000, message.id);
  writer.close();
  const reader = new BridgeStore(path, { readOnly: true });
  assert.equal(reader.outbox("asker", {}).entries.find((e) => e.id === message.id)?.deliveryState, "queued");
  reader.close();
  const normal = new BridgeStore(path);
  assert.equal(normal.outbox("asker", {}).entries.find((e) => e.id === message.id)?.deliveryState, "expired");
  normal.close();
});

// D244: a script identity belongs to no session.
import { CallerIdentity, IdentityError } from "../src/identity.js";
import { agentsView } from "../src/views.js";

test("a script identity is recorded with host script and no wake binding; registering again is a no-op (D244)", () => {
  const store = new BridgeStore(":memory:");
  const first = store.registerScriptIdentity("di-patrol");
  assert.deepEqual(first.host, { app: "script", sessionId: "di-patrol" });
  assert.equal(store.wakes.target("di-patrol"), null);
  assert.deepEqual(store.registerScriptIdentity("di-patrol").host, first.host);
  store.close();
});

test("a session's name cannot become a script identity, nor a retired one (D244)", () => {
  const store = new BridgeStore(":memory:");
  store.register("hub", [], { app: "claude", sessionId: "s1" });
  assert.throws(() => store.registerScriptIdentity("hub"), /registered by a claude session/);
  store.registerScriptIdentity("old-patrol");
  store.retire("old-patrol", { by: "user" });
  assert.throws(() => store.registerScriptIdentity("old-patrol"), /retired/);
  store.close();
});

test("no session may act as a script identity (D244)", () => {
  const store = new BridgeStore(":memory:");
  const agent = store.registerScriptIdentity("di-patrol");
  for (const caller of [new CallerIdentity({ app: "claude", sessionId: "s1" }), new CallerIdentity(null)]) {
    assert.equal(caller.owns("di-patrol", agent), false);
    assert.throws(() => caller.require("di-patrol", agent, "send as"), (error: unknown) =>
      error instanceof IdentityError && /script identity/.test(error.message));
  }
  store.close();
});

test("a script identity's presence is unknown, never looked up (D244)", async () => {
  const store = new BridgeStore(":memory:");
  store.registerScriptIdentity("di-patrol");
  const view = await agentsView(store, {});
  const entry = view.agents.find((a) => a.name === "di-patrol") as { presence?: unknown } | undefined;
  assert.deepEqual(entry?.presence, { state: "unknown", detail: "script identity" });
  store.close();
});

// agent-relay post-090-bridge D251: a session sending to a script identity is told nothing wakes it.
import { checkRecipient } from "../src/addressing.js";

test("a send to a script identity warns that nothing wakes it, instead of the stale-binding warning (D251)", async () => {
  const store = new BridgeStore(":memory:");
  store.registerScriptIdentity("di-patrol");
  store.register("hub", [], { app: "claude", sessionId: "s1" });
  store.register("worker", [], { app: "codex", sessionId: "t1" });
  const later = Date.now() + 3 * 24 * 3_600_000;
  const script = await checkRecipient(store, "di-patrol", { now: later });
  assert.equal(script.ok, true);
  assert.equal(script.warnings.filter((w) => /script identity/.test(w)).length, 1);
  assert.match(script.warnings.join("\n"), /nothing wakes it/);
  assert.doesNotMatch(script.warnings.join("\n"), /no background ping binding/);
  for (const name of ["hub", "worker"]) {
    const other = await checkRecipient(store, name, { now: later });
    assert.doesNotMatch(other.warnings.join("\n"), /script identity/);
  }
  store.close();
});
