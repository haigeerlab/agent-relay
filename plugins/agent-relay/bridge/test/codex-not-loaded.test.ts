// agent-relay codex-not-loaded D200: a Codex task the ChatGPT app does not answer for (usually not opened since the app
// started; a deleted task or a wrong id looks the same) is reported as such, with what to do, never as a lost connection.
import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, rmSync } from "node:fs";
import { createServer, type Server } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { CODEX_NOT_LOADED, wakeCodex } from "../src/codex-wake.js";
import { codexNoticeReason } from "../src/wake-dispatcher.js";
import { codexOwner, codexPresence } from "../src/presence.js";
import type { WakeJob } from "../src/wake-queue.js";

const FAST = { responseTimeoutMs: 200 };
const job: WakeJob = { id: 1, messageId: 7, mailboxPath: "/test/bridge.sqlite", agent: "cx",
  target: { app: "codex", sessionId: "not-opened-task" }, state: "sending", attemptId: "attempt-1",
  attempts: 1, retryAt: 0, createdAt: 0, detail: "" };

/** A Codex app that completes the handshake but never answers about these threads (as for a task it has not loaded). */
async function silentCodex(): Promise<{ path: string; server: Server; dir: string; asked: string[] }> {
  const dir = mkdtempSync(join(tmpdir(), "codex-silent-"));
  chmodSync(dir, 0o700);
  const path = join(dir, "ipc.sock");
  const asked: string[] = [];
  const server = createServer(socket => {
    let buffer = Buffer.alloc(0);
    socket.on("error", () => {});
    socket.on("data", chunk => {
      buffer = Buffer.concat([buffer, chunk]);
      while (buffer.length >= 4) {
        const size = buffer.readUInt32LE(0);
        if (buffer.length < size + 4) return;
        const r = JSON.parse(buffer.subarray(4, size + 4).toString());
        buffer = buffer.subarray(size + 4);
        asked.push(r.method);
        if (r.method !== "initialize") continue; // silence about the thread
        const body = Buffer.from(JSON.stringify({ type: "response", requestId: r.requestId, resultType: "success",
          result: { clientId: "test-client" } }));
        const header = Buffer.alloc(4); header.writeUInt32LE(body.length);
        socket.write(Buffer.concat([header, body]));
      }
    });
  });
  await new Promise<void>(ok => server.listen(path, ok));
  chmodSync(path, 0o600);
  return { path, server, dir, asked };
}

async function close(fake: { server: Server; dir: string }): Promise<void> {
  await new Promise<void>(ok => fake.server.close(() => ok()));
  rmSync(fake.dir, { recursive: true, force: true });
}

test("no answer about the task: pending offline, saying it is usually not opened yet and what to do otherwise", { skip: process.platform === "win32" }, async () => {
  const fake = await silentCodex();
  try {
    for (const sessionId of ["not-opened-task", "00000000-0000-7000-8000-000000000000"]) {
      const result = await wakeCodex({ ...job, target: { app: "codex", sessionId } }, fake.path, FAST);
      assert.deepEqual(result, { state: "pending", reason: "offline", detail: CODEX_NOT_LOADED }, sessionId);
    }
    assert.ok(!fake.asked.includes("thread-follower-start-turn"), "nothing was submitted");
  } finally { await close(fake); }
  assert.match(CODEX_NOT_LOADED, /did not answer/);
  assert.match(CODEX_NOT_LOADED, /usually because it was not opened since the app started/);
  assert.match(CODEX_NOT_LOADED, /open it/);
  assert.match(CODEX_NOT_LOADED, /deleted/, "a task that no longer exists is covered too");
  // A socket that cannot be reached keeps the old words.
  const missing = await wakeCodex(job, join(tmpdir(), "no-such-dir", "ipc.sock"), FAST);
  assert.deepEqual(missing, { state: "pending", reason: "offline", detail: "Codex local connection unavailable" });
});

test("presence: not-loaded when the app is silent, unknown without the app", { skip: process.platform === "win32" }, async () => {
  const fake = await silentCodex();
  try {
    const owner = await codexOwner("not-opened-task", fake.path, FAST);
    assert.equal(owner, "not-loaded");
    const presence = codexPresence(owner);
    assert.equal(presence.state, "not-loaded");
    assert.equal(presence.detail, CODEX_NOT_LOADED);
  } finally { await close(fake); }
  assert.equal(await codexOwner("t", join(tmpdir(), "no-such-dir", "ipc.sock"), FAST), null);
  assert.equal(codexPresence(null).state, "unknown");
  assert.equal(codexPresence(true).state, "running");
  assert.equal(codexPresence(false).state, "stopped");
});

test("the Codex notice for such a ping tells the user to open the task", () => {
  const reason = codexNoticeReason({ state: "pending", reason: "offline", detail: CODEX_NOT_LOADED });
  assert.match(reason ?? "", /open it in the ChatGPT app/);
  assert.equal(codexNoticeReason({ state: "pending", reason: "offline", detail: "Codex local connection unavailable" }),
    "Codex is not running; the message waits");
});
