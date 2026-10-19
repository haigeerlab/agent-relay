// agent-relay codex-approval-presence D232, D234: a Codex task the ChatGPT app shows waiting for the user is seen as
// waiting in bridge_agents, bridge_send's warning and bridge_outbox awaitingReply; nothing of its conversation is kept.
import assert from "node:assert/strict";
import { readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { awaitingCodexPresence } from "../src/awaiting-reply.js";
import { BridgeStore } from "../src/bridge-store.js";
import { fakeCodexApp, snapshot } from "./support/fake-codex-app.js";
import { session } from "./support/session.js";

const at = Date.UTC(2026, 9, 19, 6, 23, 24);
const pending = (method: string) => ({ method, id: 1, params: { startedAtMs: at, command: "MARKER-command",
  reason: "MARKER-reason", cwd: "/MARKER-cwd" } });

function filesUnder(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? filesUnder(path) : [path];
  });
}

test("bridge_agents, bridge_send and bridge_outbox see a Codex task waiting for the user", { skip: process.platform !== "darwin" }, async () => {
  const home = mkdtempSync("/tmp/ar-cap-");
  const app = await fakeCodexApp({ home, onFollow: (id) => [snapshot(id, {
    requests: [pending(id === "approval-task" ? "item/commandExecution/requestApproval" : "item/tool/requestUserInput")],
    turns: [{ items: [{ text: "MARKER-turn" }] }],
  })] });
  const store = new BridgeStore(join(home, "bridge.sqlite"));
  store.register("cx-approval", [], { app: "codex", sessionId: "approval-task" });
  store.register("cx-input", [], { app: "codex", sessionId: "input-task" });
  store.close();
  const claude = await session(home, "claude-sender");
  try {
    assert.ok((await claude.call("bridge_register", { agent: "sender" })).ok);
    const agents = (await claude.call("bridge_agents", {})).json().agents;
    const approval = agents.find((a: any) => a.name === "cx-approval").presence;
    assert.deepEqual(approval, { state: "waiting-approval", since: new Date(at).toISOString(),
      detail: "waiting for your approval to run a command in its Codex task" });
    assert.equal(agents.find((a: any) => a.name === "cx-input").presence.state, "waiting-input");

    const sent = (await claude.call("bridge_send", { from: "sender", to: "cx-approval", body: "hi", wake: false,
      expectsReply: true })).json();
    assert.ok(sent.warnings.some((w: string) => /"cx-approval" is waiting for the user's approval/.test(w)),
      JSON.stringify(sent.warnings));

    const outbox = (await claude.call("bridge_outbox", { agent: "sender", awaitingReply: true })).json();
    assert.equal(outbox.entries[0].recipientPresence.state, "waiting-approval");

    // D234: no conversation content anywhere the bridge writes or answers.
    for (const file of filesUnder(home).filter((f) => !f.endsWith(".sock"))) {
      assert.ok(!readFileSync(file).includes("MARKER"), `conversation content found in ${file}`);
    }
  } finally {
    await claude.close();
    await app.close();
    rmSync(home, { recursive: true, force: true });
  }
});

test("the awaiting view keeps reporting a silent app as unknown and reads a waiting task", { skip: process.platform === "win32" }, async () => {
  const app = await fakeCodexApp({ onFollow: (id) => [snapshot(id, { requests: [pending("item/fileChange/requestApproval")] })] });
  try {
    assert.equal((await awaitingCodexPresence("t", app.path)).state, "waiting-approval");
  } finally {
    await app.close();
  }
  const silent = await fakeCodexApp({ owner: "silent" });
  try {
    assert.equal((await awaitingCodexPresence("t", silent.path)).state, "unknown");
  } finally {
    await silent.close();
  }
});
