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
  assert.equal(parsed.whoami.note, "A script is not a session; it acts only as a script identity (send, inbox, ack).");
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
  // script-inbox-ack D274
  assert.match(preview.stdout, /only the agent-relay CLI \(send, inbox, ack\) acts as it/);
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
  assert.match(asSession.stderr, /"hub" is a session identity/);
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

test("send to another script identity carries the script warning (post-090-bridge D251)", async () => {
  const { dbPath, env } = setup();
  const seed = new BridgeStore(dbPath);
  seed.registerScriptIdentity("di-patrol");
  seed.registerScriptIdentity("di-report");
  seed.close();
  const sent = await cli(["send", "--from", "di-patrol", "--to", "di-report", "--no-wake"], env, "status");
  assert.equal(sent.code, 0, sent.stderr);
  assert.match(JSON.parse(sent.stdout).warnings.join("\n"), /"di-report" is a script identity/);
});

// Review of #164 (S47): a step after the commit that fails leaves the stored message, exit code 0 and a warning.
test("send whose step after the commit fails exits 0 with a do-not-resend warning and stores one message", async () => {
  const { dbPath, env } = setup();
  const seed = new BridgeStore(dbPath);
  seed.registerScriptIdentity("di-patrol");
  seed.register("dev");
  // Recording the sender's activity is the first step after the commit; make it fail as a busy database would.
  seed.database.exec(`CREATE TRIGGER fail_touch BEFORE UPDATE OF last_seen ON agents WHEN NEW.name = 'di-patrol'
    BEGIN SELECT RAISE(ABORT, 'database is locked'); END`);
  seed.close();
  const sent = await cli(["send", "--from", "di-patrol", "--to", "dev", "--no-wake"], env, "status");
  assert.equal(sent.code, 0, sent.stderr);
  const result = JSON.parse(sent.stdout);
  assert.ok(result.warnings?.some((warning: string) =>
    warning.includes(`Saved as #${result.id}`) && /Do not send it again/.test(warning)), sent.stdout);
  const db = new DatabaseSync(dbPath, { readOnly: true });
  assert.deepEqual(db.prepare("SELECT id FROM messages WHERE from_agent = 'di-patrol'").all().map((row) => Number(row.id)),
    [result.id]);
  db.close();
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

// agent-relay script-inbox-ack D271–D273: a script identity reads and acknowledges its own inbox through the CLI.
function inboxSeed(dbPath: string): { direct: number; broadcast: number } {
  const seed = new BridgeStore(dbPath);
  seed.register("hub", [], { app: "claude", sessionId: "s1" });
  seed.registerScriptIdentity("di-patrol");
  const direct = seed.send({ fromAgent: "hub", toAgent: "di-patrol", body: "please check #12", expectsReply: true }).id;
  const broadcast = seed.send({ fromAgent: "hub", toAgent: "*", body: "everyone: release tonight" }).id;
  seed.close();
  return { direct, broadcast };
}

test("inbox lists a script identity's direct messages and broadcasts and records the read (D271)", async () => {
  const { dbPath, env } = setup();
  const { direct, broadcast } = inboxSeed(dbPath);
  const run = await cli(["inbox", "di-patrol"], env);
  assert.equal(run.code, 0, run.stderr);
  const result = JSON.parse(run.stdout);
  assert.equal(result.agent, "di-patrol");
  assert.equal(result.readRecorded, true);
  assert.equal("readNote" in result, false);
  assert.deepEqual(result.messages.map((m: { id: number }) => m.id), [direct, broadcast]);
  assert.equal(result.messages[0].body, "please check #12");
  assert.equal(result.messages[0].deliveryState, "accepted");
  for (const field of ["count", "totalUnread", "hasMore", "nextAfterId"]) assert.ok(field in result, field);
  const store = new BridgeStore(dbPath);
  try {
    const row = store.database.prepare("SELECT read_at, delivery_state FROM messages WHERE id = ?").get(direct) as
      { read_at: number | null; delivery_state: string };
    assert.notEqual(row.read_at, null);
    assert.equal(row.delivery_state, "accepted");
    // Reading is not handling: both still wait for an acknowledgement.
    assert.equal(store.countUnread("di-patrol"), 2);
  } finally {
    store.close();
  }
  const filtered = JSON.parse((await cli(["inbox", "di-patrol", "--from-agent", "nobody"], env)).stdout);
  assert.equal(filtered.count, 0);
});

test("inbox reads a long body in parts, with continue lines that name the CLI (D271)", async () => {
  const { dbPath, env } = setup();
  const seed = new BridgeStore(dbPath);
  seed.register("hub", [], { app: "claude", sessionId: "s1" });
  seed.registerScriptIdentity("di-patrol");
  const body = "x".repeat(5000);
  const id = seed.send({ fromAgent: "hub", toAgent: "di-patrol", body }).id;
  seed.close();
  const page = JSON.parse((await cli(["inbox", "di-patrol", "--max-chars", "1000"], env)).stdout);
  assert.equal(page.messages[0].bodyTruncated, true);
  const offset = page.messages[0].nextOffset as number;
  assert.deepEqual(page.continue, [`Message #${id} is longer than this page; read the rest with agent-relay inbox ` +
    `di-patrol --message-id ${id} --body-offset ${offset}`]);
  const part = await cli(["inbox", "di-patrol", "--message-id", String(id), "--body-offset", String(offset)], env);
  assert.equal(part.code, 0, part.stderr);
  const message = JSON.parse(part.stdout).message;
  assert.equal(message.bodyOffset, offset);
  assert.equal(message.body, body.slice(offset, offset + message.body.length));
  const past = await cli(["inbox", "di-patrol", "--message-id", String(id), "--body-offset", "6000"], env);
  assert.equal(past.code, 1);
  assert.match(past.stderr, /past the end/);
});

test("ack acknowledges a direct message and a broadcast, so nothing blocks retirement (D272)", async () => {
  const { dbPath, env } = setup();
  const { direct, broadcast } = inboxSeed(dbPath);
  const run = await cli(["ack", "di-patrol", "--ids", `${direct},${broadcast}`], env);
  assert.equal(run.code, 0, run.stderr);
  assert.deepEqual(JSON.parse(run.stdout), { acknowledged: 2, remainingUnread: 0 });
  const again = JSON.parse((await cli(["ack", "di-patrol", "--ids", String(direct)], env)).stdout);
  assert.deepEqual(again, { acknowledged: 0, remainingUnread: 0 });
  const store = new BridgeStore(dbPath);
  try {
    // native_collaboration_retire.py blocks on the bridge's unread rule (cleanup-gaps D59): nothing is left.
    assert.equal(store.countUnread("di-patrol"), 0);
  } finally {
    store.close();
  }
  const empty = JSON.parse((await cli(["inbox", "di-patrol"], env)).stdout);
  assert.equal(empty.count, 0);
});

test("inbox and ack act only as a live script identity and change nothing otherwise (D273)", async () => {
  const { dbPath, env } = setup();
  const { direct } = inboxSeed(dbPath);
  const seed = new BridgeStore(dbPath);
  seed.register("dev");
  seed.send({ fromAgent: "hub", toAgent: "dev", body: "for dev" });
  seed.registerScriptIdentity("old-patrol");
  seed.retire("old-patrol", { by: "operator" });
  seed.close();
  const before = snapshot(dbPath);
  const session = /"(hub|dev)" is a session identity: only its own session reads its inbox as itself and acknowledges its messages \(bridge_inbox, bridge_ack\)\. The agent-relay CLI acts only as a script identity\./;
  for (const args of [["inbox", "hub"], ["inbox", "dev"], ["ack", "dev", "--ids", String(direct)],
    ["send", "--from", "hub", "--to", "dev"]]) {
    const run = await cli(args, env, "hi");
    assert.equal(run.code, 1, args.join(" "));
    assert.match(run.stderr, session, args.join(" "));
    assert.equal(run.stdout, "");
  }
  const unknown = await cli(["ack", "nobody", "--ids", "1"], env);
  assert.equal(unknown.code, 1);
  assert.match(unknown.stderr, /"nobody" is not a script identity; register one with register-script-identity/);
  const retired = await cli(["inbox", "old-patrol"], env);
  assert.equal(retired.code, 1);
  assert.match(retired.stderr, /"old-patrol" was retired/);
  assert.deepEqual(snapshot(dbPath), before);
});
