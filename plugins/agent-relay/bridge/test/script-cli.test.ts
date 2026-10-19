// agent-relay script-access D241–D244: the runtime CLI's script commands, run as a child process.
import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { createConnection, createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { BridgeStore } from "../src/bridge-store.js";
import { agentsView, outboxView } from "../src/views.js";

const projectRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

interface Run { code: number | null; stdout: string; stderr: string }

function cli(args: string[], env: Record<string, string>, input?: string): Promise<Run> {
  return new Promise((done) => {
    const child = spawn(process.execPath, ["--import", "tsx", "src/cli.ts", ...args],
      { cwd: projectRoot, env: { PATH: process.env.PATH ?? "", ...env } });
    let stdout = "", stderr = "";
    child.stdout.on("data", (d) => { stdout += d; });
    child.stderr.on("data", (d) => { stderr += d; });
    child.on("close", (code) => done({ code, stdout, stderr }));
    child.stdin.end(input ?? "");
  });
}

function setup(): { dbPath: string; env: Record<string, string>; home: string } {
  const dir = mkdtempSync(join(tmpdir(), "ar-cli-"));
  const home = join(dir, "home");
  mkdirSync(join(home, ".claude", "sessions"), { recursive: true });
  const dbPath = join(dir, "bridge.sqlite");
  return { dbPath, home, env: { HOME: home, BRIDGE_DB_PATH: dbPath, XDG_DATA_HOME: join(dir, "data") } };
}

function snapshot(dbPath: string) {
  const db = new DatabaseSync(dbPath, { readOnly: true });
  const rows = (sql: string) => JSON.stringify(db.prepare(sql).all());
  const result = [rows("SELECT id, read_at, delivery_state FROM messages ORDER BY id"),
    rows("SELECT * FROM acknowledgements ORDER BY message_id"), rows("SELECT name, last_seen, host_app FROM agents ORDER BY name"),
    rows("SELECT id, state FROM wake_jobs ORDER BY id")];
  db.close();
  return result;
}

test("agents, outbox and sessions print the views and leave the mailbox unchanged (D241, D242)", async () => {
  const { dbPath, env } = setup();
  const seed = new BridgeStore(dbPath);
  for (const name of ["asker", "helper"]) seed.register(name);
  seed.send({ fromAgent: "asker", toAgent: "helper", body: "q", expectsReply: true });
  seed.close();
  const before = snapshot(dbPath);
  const agents = await cli(["agents"], env);
  const outbox = await cli(["outbox", "asker"], env);
  const sessions = await cli(["sessions"], env);
  for (const run of [agents, outbox, sessions]) assert.equal(run.code, 0, run.stderr);
  assert.deepEqual(snapshot(dbPath), before, "nothing in the mailbox changed");
  const store = new BridgeStore(dbPath, { readOnly: true });
  assert.deepEqual(JSON.parse(agents.stdout), await agentsView(store, {}));
  assert.deepEqual(JSON.parse(outbox.stdout), await outboxView(store, { agent: "asker" }));
  store.close();
  const parsed = JSON.parse(sessions.stdout);
  assert.equal(parsed.thisSession, null);
  assert.equal(parsed.codexSessionId, null);
  assert.deepEqual(parsed.claude, []);
});

test("a missing mailbox exits non-zero with one sentence on stderr (D242)", async () => {
  const { env } = setup();
  const run = await cli(["agents"], env);
  assert.notEqual(run.code, 0);
  assert.equal(run.stdout, "");
  assert.equal(run.stderr.trim().split("\n").length, 1);
  assert.match(run.stderr, /No mailbox/);
});

test("register-script-identity changes nothing without --confirm (D244)", async () => {
  const { dbPath, env } = setup();
  new BridgeStore(dbPath).close();
  const preview = await cli(["register-script-identity", "di-patrol"], env);
  assert.equal(preview.code, 0, preview.stderr);
  assert.match(preview.stdout, /--confirm/);
  let store = new BridgeStore(dbPath, { readOnly: true });
  assert.equal(store.getAgent("di-patrol"), undefined);
  store.close();
  const done = await cli(["register-script-identity", "di-patrol", "--confirm"], env);
  assert.equal(done.code, 0, done.stderr);
  store = new BridgeStore(dbPath, { readOnly: true });
  assert.deepEqual(store.getAgent("di-patrol")?.host, { app: "script", sessionId: "di-patrol" });
  store.close();
});

test("send refuses a session's name, a body on argv, and returns bridge_send's object (D243, D244)", async () => {
  const { dbPath, env } = setup();
  const seed = new BridgeStore(dbPath);
  seed.registerScriptIdentity("di-patrol");
  seed.register("hub", [], { app: "claude", sessionId: "s1" });
  seed.register("dev");
  seed.close();
  const asSession = await cli(["send", "--from", "hub", "--to", "dev"], env, "hi");
  assert.notEqual(asSession.code, 0);
  assert.match(asSession.stderr, /not a script identity/);
  const onArgv = await cli(["send", "--from", "di-patrol", "--to", "dev", "the body"], env);
  assert.notEqual(onArgv.code, 0);
  assert.match(onArgv.stderr, /stdin|--body-file/);
  const sent = await cli(["send", "--from", "di-patrol", "--to", "dev", "--expects-reply"], env, "please look");
  assert.equal(sent.code, 0, sent.stderr);
  const result = JSON.parse(sent.stdout);
  assert.equal(result.fromAgent, "di-patrol");
  assert.equal(result.bodyLength, "please look".length);
  assert.equal(result.expectsReply, true);
  assert.equal("body" in result, false);
  const file = join(dirname(dbPath), "body.txt");
  writeFileSync(file, "from a file", { mode: 0o600 });
  const fromFile = await cli(["send", "--from", "di-patrol", "--to", "dev", "--body-file", file, "--no-wake"], env);
  assert.equal(fromFile.code, 0, fromFile.stderr);
  assert.equal(JSON.parse(fromFile.stdout).bodyLength, "from a file".length);
});

async function fakeClaudeSession(home: string, sessionId: string, { reply = true }: { reply?: boolean } = {}) {
  const root = join(home, ".claude", "sessions");
  const directory = "/tmp/cc-socks-" + process.getuid!();
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const path = join(directory, process.pid + "-" + randomBytes(4).toString("hex") + ".sock");
  const procStart = execFileSync("/bin/ps", ["-p", String(process.pid), "-o", "lstart="],
    { encoding: "utf8", env: { ...process.env, TZ: "UTC", LC_ALL: "C" } }).trim();
  const token = randomBytes(16).toString("hex");
  writeFileSync(join(root, process.pid + ".json"), JSON.stringify({ pid: process.pid, sessionId,
    name: "fixture", cwd: root, procStart, messagingSocketPath: path, version: "2.1.260", peerProtocol: 1 }), { mode: 0o644 });
  writeFileSync(join(root, process.pid + "." + createHash("sha256").update(resolve(path)).digest("hex") + ".key"),
    JSON.stringify({ peerToken: token, procStart }), { mode: 0o600 });
  const state = { transmissions: 0 };
  const server = createServer((socket) => {
    let buffer = "";
    socket.on("error", () => {});
    socket.on("data", (data) => {
      buffer += data.toString();
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const packet = JSON.parse(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1);
        if (packet.type !== "user") continue;
        state.transmissions++;
        if (!reply) continue;
        const answer = createConnection(packet.from.slice(4));
        answer.on("error", () => {});
        answer.once("connect", () => answer.end(JSON.stringify({ type: "control", action: "peer_message_status",
          status: "delivered", orig_msg_id: packet.msg_id }) + "\n"));
      }
    });
  });
  await new Promise<void>((ok) => server.listen(path, ok));
  chmodSync(path, 0o600);
  return { state, root, close: () => new Promise<void>((ok) => server.close(() => ok())) };
}

test("send pings a wake-bound Claude session once before exiting (D243)", { skip: process.platform !== "darwin" }, async () => {
  const { dbPath, env, home } = setup();
  const fake = await fakeClaudeSession(home, "cli-test-session");
  try {
    const seed = new BridgeStore(dbPath);
    seed.registerScriptIdentity("di-patrol");
    seed.register("dev", [], { app: "claude", sessionId: "cli-test-session" });
    seed.wakes.bind("dev", { app: "claude", sessionId: "cli-test-session" });
    seed.close();
    const sent = await cli(["send", "--from", "di-patrol", "--to", "dev"], env, "wake up");
    assert.equal(sent.code, 0, sent.stderr);
    assert.equal(fake.state.transmissions, 1);
    assert.equal(JSON.parse(sent.stdout).wake?.state, "accepted");
  } finally {
    await fake.close();
  }
});

test("send's flush and a running bridge's dispatcher ping one message once (D243, plan risk)", { skip: process.platform !== "darwin" }, async () => {
  const { dbPath, env, home } = setup();
  const fake = await fakeClaudeSession(home, "race-session");
  const seed = new BridgeStore(dbPath);
  seed.registerScriptIdentity("di-patrol");
  seed.register("dev", [], { app: "claude", sessionId: "race-session" });
  seed.wakes.bind("dev", { app: "claude", sessionId: "race-session" });
  seed.close();
  const { WakeDispatcher } = await import("../src/wake-dispatcher.js");
  const running = new BridgeStore(dbPath);
  const previousHome = process.env.HOME;
  process.env.HOME = home;
  const dispatcher = new WakeDispatcher(running);
  try {
    const sending = cli(["send", "--from", "di-patrol", "--to", "dev"], env, "once");
    for (let i = 0; i < 15; i++) {
      await dispatcher.flush();
      await new Promise((ok) => setTimeout(ok, 100));
    }
    const sent = await sending;
    assert.equal(sent.code, 0, sent.stderr);
    for (let i = 0; i < 5; i++) await dispatcher.flush();
    assert.equal(fake.state.transmissions, 1);
  } finally {
    process.env.HOME = previousHome;
    await dispatcher.close();
    running.close();
    await fake.close();
  }
});

test("send to a session that never sends a receipt pings once and leaves the wake unknown (review of #149)", { skip: process.platform !== "darwin" }, async () => {
  const { CLAUDE_AWAITING_RECEIPT } = await import("../src/claude-wake.js");
  const { dbPath, env, home } = setup();
  const fake = await fakeClaudeSession(home, "silent-session", { reply: false });
  try {
    const seed = new BridgeStore(dbPath);
    seed.registerScriptIdentity("di-patrol");
    seed.register("dev", [], { app: "claude", sessionId: "silent-session" });
    seed.wakes.bind("dev", { app: "claude", sessionId: "silent-session" });
    seed.close();
    const sent = await cli(["send", "--from", "di-patrol", "--to", "dev"], env, "no receipt");
    assert.equal(sent.code, 0, sent.stderr);
    assert.equal(fake.state.transmissions, 1);
    const wake = JSON.parse(sent.stdout).wake;
    assert.equal(wake?.state, "unknown");
    assert.equal(wake?.detail, CLAUDE_AWAITING_RECEIPT);
  } finally {
    await fake.close();
  }
});
