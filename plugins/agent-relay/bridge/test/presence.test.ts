// agent-relay presence-and-approval D146: who is running, stopped or waiting for the user, read from the hosts.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { claudeSessions, type ClaudeSession } from "../src/claude-wake.js";
import { claudePresence, codexOwner } from "../src/presence.js";
import { session } from "./support/session.js";

function live(overrides: Partial<ClaudeSession>): ClaudeSession {
  return { pid: 1, sessionId: "internal-1", bridgeSessionId: "desktop-1", cwd: "/p", name: "n",
    messagingSocketPath: "/tmp/cc-socks/1.sock", procStart: "x", version: "2", peerProtocol: 1, ...overrides };
}

test("a live Claude session maps to running, waiting-approval or waiting-input; a missing one is stopped", () => {
  const at = Date.UTC(2026, 9, 9, 2, 12, 10);
  assert.deepEqual(claudePresence("desktop-1", [live({ status: "idle" })]), { state: "running" });
  assert.deepEqual(claudePresence("internal-1", [live({ status: "busy", statusUpdatedAt: at })]),
    { state: "running", since: "2026-10-09T02:12:10.000Z" });
  assert.deepEqual(claudePresence("desktop-1", [live({ status: "waiting", waitingFor: "permission prompt", statusUpdatedAt: at })]),
    { state: "waiting-approval", since: "2026-10-09T02:12:10.000Z", detail: "permission prompt" });
  assert.deepEqual(claudePresence("desktop-1", [live({ status: "waiting", waitingFor: "user input" })]),
    { state: "waiting-input", detail: "user input" });
  assert.deepEqual(claudePresence("desktop-1", [live({ status: "waiting" })]), { state: "waiting-input" });
  assert.deepEqual(claudePresence("desktop-1", [live({ status: "something-new" })]), { state: "running" });
  assert.deepEqual(claudePresence("other", [live({ status: "idle" })]), { state: "stopped" });
  assert.deepEqual(claudePresence("desktop-1", []), { state: "stopped" });
  assert.equal(claudePresence("desktop-1", null).state, "unknown");
});

test("the registry's status, time and reason are read; malformed ones are ignored", { skip: process.platform !== "darwin" }, async () => {
  const root = mkdtempSync(join(tmpdir(), "presence-registry-"));
  const directory = "/tmp/cc-socks-" + process.getuid!();
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const path = join(directory, process.pid + "-" + randomBytes(4).toString("hex") + ".sock");
  const procStart = execFileSync("/bin/ps", ["-p", String(process.pid), "-o", "lstart="],
    { encoding: "utf8", env: { ...process.env, TZ: "UTC", LC_ALL: "C" } }).trim();
  const server = createServer(() => {});
  await new Promise<void>(ok => server.listen(path, ok));
  chmodSync(path, 0o600);
  const base = { pid: process.pid, sessionId: "internal-p", bridgeSessionId: "desktop-p", name: "fixture", cwd: root,
    procStart, messagingSocketPath: path, version: "2.1.295", peerProtocol: 1 };
  try {
    writeFileSync(join(root, process.pid + ".json"), JSON.stringify({ ...base, status: "waiting",
      statusUpdatedAt: 1791511930012, waitingFor: "permission prompt" }));
    const [found] = await claudeSessions(root);
    assert.equal(found.status, "waiting");
    assert.equal(found.statusUpdatedAt, 1791511930012);
    assert.equal(found.waitingFor, "permission prompt");
    writeFileSync(join(root, process.pid + ".json"), JSON.stringify({ ...base, status: 7, statusUpdatedAt: "soon",
      waitingFor: { x: 1 } }));
    const [odd] = await claudeSessions(root);
    assert.equal(odd.status, undefined);
    assert.equal(odd.statusUpdatedAt, undefined);
    assert.equal(odd.waitingFor, undefined);
  } finally {
    await new Promise<void>(ok => server.close(() => ok()));
    rmSync(root, { recursive: true, force: true });
  }
});

async function fakeCodex(owner: "owner" | "none"): Promise<{ path: string; server: Server; dir: string }> {
  const dir = mkdtempSync(join(tmpdir(), "presence-codex-"));
  chmodSync(dir, 0o700);
  const path = join(dir, "ipc.sock");
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
        const result = r.method === "initialize" ? { clientId: "test-client" } : {};
        const body = Buffer.from(JSON.stringify({ type: "response", requestId: r.requestId, resultType: "success", result,
          ...(r.method === "thread-owner-discovery" && owner === "owner" ? { handledByClientId: "owner" } : {}) }));
        const header = Buffer.alloc(4); header.writeUInt32LE(body.length);
        socket.write(Buffer.concat([header, body]));
      }
    });
  });
  await new Promise<void>(ok => server.listen(path, ok));
  chmodSync(path, 0o600);
  return { path, server, dir };
}

test("a Codex task is running with a connected owner, stopped without one, unknown without the app", { skip: process.platform === "win32" }, async () => {
  for (const [owner, expected] of [["owner", true], ["none", false]] as const) {
    const fake = await fakeCodex(owner);
    try {
      assert.equal(await codexOwner("thread-1", fake.path), expected);
    } finally {
      await new Promise<void>(ok => fake.server.close(() => ok()));
      rmSync(fake.dir, { recursive: true, force: true });
    }
  }
  assert.equal(await codexOwner("thread-1", join(tmpdir(), "no-such-dir", "ipc.sock")), null);
});

test("bridge_agents shows presence for every agent", async () => {
  const dir = mkdtempSync(join(tmpdir(), "presence-agents-"));
  const claude = await session(dir, "claude-gone");
  try {
    assert.ok((await claude.call("bridge_register", { agent: "cc" })).ok);
    const listed = (await claude.call("bridge_agents", {})).json();
    const cc = listed.agents.find((a: any) => a.name === "cc");
    // No registry file under this HOME: the Claude session is not running (unknown off macOS).
    assert.equal(cc.presence.state, process.platform === "darwin" ? "stopped" : "unknown");
    for (const agent of listed.agents) assert.ok(["running", "waiting-approval", "waiting-input", "stopped", "unknown"]
      .includes(agent.presence?.state), JSON.stringify(agent));
  } finally {
    await claude.close();
  }
});
