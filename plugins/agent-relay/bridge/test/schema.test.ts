import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readdirSync, statSync, writeFileSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { DATA_DIR_NAME } from "../src/fs-safety.js";
import { SCHEMA_VERSION, schemaVersion } from "../src/schema.js";

/** Exactly the tables and statements bridge 0.3.0 created and ran. */
const LEGACY_SCHEMA = `
  CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, from_agent TEXT NOT NULL, to_agent TEXT NOT NULL,
    body TEXT NOT NULL, thread_id TEXT, idempotency_key TEXT, created_at TEXT NOT NULL);
  CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_idempotency ON messages (from_agent, idempotency_key) WHERE idempotency_key IS NOT NULL;
  CREATE INDEX IF NOT EXISTS idx_messages_to ON messages (to_agent);
  CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages (thread_id);
  CREATE TABLE IF NOT EXISTS acknowledgements (
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE, agent TEXT NOT NULL,
    acked_at TEXT NOT NULL, PRIMARY KEY (message_id, agent));
  CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY, capabilities TEXT NOT NULL, registered_at TEXT NOT NULL, last_seen TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS orchestration_runs (
    id TEXT PRIMARY KEY, coordinator_agent TEXT NOT NULL, project_path TEXT NOT NULL, worktree_path TEXT NOT NULL,
    thread_id TEXT NOT NULL, task TEXT NOT NULL, status TEXT NOT NULL, round INTEGER NOT NULL DEFAULT 0,
    max_rounds INTEGER NOT NULL, codex_session_id TEXT, latest_response TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS orchestration_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES orchestration_runs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
  CREATE INDEX IF NOT EXISTS idx_orchestration_events_run ON orchestration_events (run_id, id);
  CREATE TABLE IF NOT EXISTS wake_targets (agent TEXT PRIMARY KEY, target TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS wake_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER NOT NULL REFERENCES messages(id),
    agent TEXT NOT NULL, target TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', attempt_id TEXT,
    attempts INTEGER NOT NULL DEFAULT 0, retry_at INTEGER NOT NULL, created_at INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT '', UNIQUE(message_id, agent));
  CREATE INDEX IF NOT EXISTS wake_jobs_due ON wake_jobs(state, retry_at);`;

function legacyDatabase(path: string): void {
  const db = new DatabaseSync(path);
  db.exec("PRAGMA journal_mode = WAL;");
  db.exec(LEGACY_SCHEMA);
  const now = new Date().toISOString();
  db.prepare("INSERT INTO agents VALUES (?, ?, ?, ?)").run("claude-main", '["review"]', now, now);
  db.prepare("INSERT INTO agents VALUES (?, ?, ?, ?)").run("codex-main", "[]", now, now);
  db.prepare("INSERT INTO messages (from_agent, to_agent, body, thread_id, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?, ?)")
    .run("codex-main", "claude-main", "handled long ago", "t1", "k1", now);
  db.prepare("INSERT INTO messages (from_agent, to_agent, body, thread_id, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?, ?)")
    .run("codex-main", "claude-main", "still unread", "t1", "k2", now);
  db.prepare("INSERT INTO acknowledgements VALUES (1, 'claude-main', ?)").run(now);
  db.prepare(`INSERT INTO wake_jobs (message_id, agent, target, state, retry_at, created_at, detail)
    VALUES (2, 'claude-main', '{"app":"claude","sessionId":"s1"}', 'refused', 0, ?, 'Claude expired this peer message')`).run(Date.now());
  db.prepare(`INSERT INTO orchestration_runs VALUES ('old-run', 'claude-main', '/repo', '/repo', 't1', 'task', 'completed', 2, 6, 'sess', NULL, ?, ?)`)
    .run(now, now);
  db.close();
}

test("an unversioned 0.3 mailbox is backed up, then migrated without losing data", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-migrate-"));
  const path = join(dir, "bridge.sqlite");
  const backupDir = join(dir, "backups");
  legacyDatabase(path);

  const store = new BridgeStore(path, { backupDir });
  assert.deepEqual(store.migration, { from: 0, to: SCHEMA_VERSION, newer: false });
  const backups = readdirSync(backupDir);
  assert.equal(backups.length, 1);
  assert.match(backups[0] ?? "", new RegExp(`^bridge-pre-v${SCHEMA_VERSION}-from-v0-`));
  const copy = new DatabaseSync(join(backupDir, backups[0] as string), { readOnly: true });
  assert.equal((copy.prepare("SELECT COUNT(*) AS n FROM messages").get() as { n: number }).n, 2);
  copy.close();

  assert.deepEqual(store.inbox("claude-main").map((message) => message.body), ["still unread"]);
  assert.deepEqual(store.getAgent("claude-main")?.capabilities, ["review"]);
  assert.equal(store.getAgent("claude-main")?.retiredAt, null);
  assert.equal(store.getRun("old-run")?.deliveredRound, 2, "pre-v2 runs were already returned to their coordinator");
  assert.equal(store.wakes.claimFailure(), null, "historical failures must not become a burst of new notices");
  store.close();

  const reopened = new BridgeStore(path, { backupDir });
  assert.deepEqual(reopened.migration, { from: SCHEMA_VERSION, to: SCHEMA_VERSION, newer: false });
  assert.equal(readdirSync(backupDir).length, 1, "no backup when nothing changes");
  reopened.close();
});

test("bridge 0.3 processes keep working against a migrated mailbox", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-compat-"));
  const path = join(dir, "bridge.sqlite");
  legacyDatabase(path);
  new BridgeStore(path).close();

  // The statements 0.3.0 still runs in sessions that have not restarted yet.
  const legacy = new DatabaseSync(path);
  const now = new Date().toISOString();
  legacy.prepare(`INSERT INTO agents (name, capabilities, registered_at, last_seen) VALUES (?, ?, ?, ?)
    ON CONFLICT(name) DO UPDATE SET capabilities = excluded.capabilities, last_seen = excluded.last_seen`)
    .run("old-session", "[]", now, now);
  legacy.prepare("INSERT INTO messages (from_agent, to_agent, body, thread_id, idempotency_key, created_at) VALUES (?, ?, ?, ?, ?, ?)")
    .run("old-session", "claude-main", "from an old process", null, null, now);
  legacy.prepare(`INSERT OR IGNORE INTO acknowledgements (message_id, agent, acked_at)
    SELECT m.id, ?, ? FROM messages m WHERE m.id = ? AND (m.to_agent = ? OR (m.to_agent = ? AND m.from_agent != ?))`)
    .run("claude-main", now, 2, "claude-main", "*", "claude-main");
  legacy.prepare(`INSERT INTO orchestration_runs (id, coordinator_agent, project_path, worktree_path, thread_id, task,
    status, round, max_rounds, codex_session_id, latest_response, created_at, updated_at)
    VALUES ('legacy-run', 'claude-main', '/repo', '/repo', 't', 'task', 'created', 0, 6, NULL, NULL, ?, ?)`).run(now, now);
  legacy.prepare(`INSERT OR IGNORE INTO wake_jobs (message_id, agent, target, retry_at, created_at) VALUES (?, ?, ?, ?, ?)`)
    .run(3, "claude-main", '{"app":"claude","sessionId":"s1"}', Date.now(), Date.now());
  legacy.close();

  const store = new BridgeStore(path);
  assert.deepEqual(store.inbox("claude-main").map((message) => message.body), ["from an old process"]);
  const run = store.getRun("legacy-run");
  assert.equal(run?.sandboxMode, "workspace-write");
  assert.equal(run?.deliveredRound, 0);
  assert.equal(store.undeliveredRuns(new Date(Date.now() + 60_000).toISOString()).length, 0, "old-owner runs are never re-delivered");
  store.close();
});

test("mailbox files are private to their owner", { skip: process.platform === "win32" }, () => {
  const base = mkdtempSync(join(tmpdir(), "bridge-perms-"));
  const dir = join(base, DATA_DIR_NAME);
  mkdirSync(dir, { mode: 0o755 });
  chmodSync(dir, 0o755);
  const path = join(dir, "bridge.sqlite");
  writeFileSync(path, "");
  chmodSync(path, 0o644);

  const store = new BridgeStore(path);
  store.send({ fromAgent: "a", toAgent: "b", body: "private" });
  assert.equal(statSync(path).mode & 0o777, 0o600);
  assert.equal(statSync(dir).mode & 0o777, 0o700);
  store.close();

  // A caller-chosen directory keeps its own mode; only the files are tightened.
  const custom = mkdtempSync(join(tmpdir(), "bridge-custom-"));
  chmodSync(custom, 0o755);
  new BridgeStore(join(custom, "mail.sqlite")).close();
  assert.equal(statSync(custom).mode & 0o777, 0o755);
  assert.equal(statSync(join(custom, "mail.sqlite")).mode & 0o777, 0o600);
});

test("a database migrated by a newer bridge is opened in compatible mode", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-newer-"));
  const path = join(dir, "bridge.sqlite");
  new BridgeStore(path).close();
  const raw = new DatabaseSync(path);
  raw.exec(`PRAGMA user_version = ${SCHEMA_VERSION + 5}`);
  raw.close();
  const store = new BridgeStore(path);
  assert.equal(store.migration.newer, true);
  store.send({ fromAgent: "a", toAgent: "b", body: "still works" });
  assert.equal(store.inbox("b").length, 1);
  store.close();
});

test("two connections opening the same legacy file migrate it once", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-race-"));
  const path = join(dir, "bridge.sqlite");
  legacyDatabase(path);
  const first = new BridgeStore(path);
  const second = new BridgeStore(path);
  const raw = new DatabaseSync(path, { readOnly: true });
  assert.equal(schemaVersion(raw), SCHEMA_VERSION);
  raw.close();
  assert.equal(second.migration.from, SCHEMA_VERSION);
  first.close();
  second.close();
});

// agent-relay delivery-state-machine: schema v3 adds the message delivery state, additively.
const DELIVERY_COLUMNS = ["delivery_state", "delivery_changed_at", "read_at", "expires_at"];

test("v3 adds nullable delivery columns and migrates a v2 mailbox with its rows", () => {
  assert.ok(SCHEMA_VERSION >= 3);
  const dir = mkdtempSync(join(tmpdir(), "bridge-v3-"));
  const path = join(dir, "bridge.sqlite");
  const fresh = new BridgeStore(path);
  fresh.send({ fromAgent: "a", toAgent: "b", body: "before" });
  fresh.close();
  // Turn the file back into a v2 mailbox: drop the v3 columns, set the version.
  const raw = new DatabaseSync(path);
  raw.exec("DROP INDEX idx_messages_delivery");
  for (const column of DELIVERY_COLUMNS) raw.exec(`ALTER TABLE messages DROP COLUMN ${column}`);
  raw.exec("PRAGMA user_version = 2");
  raw.close();

  const store = new BridgeStore(path);
  assert.deepEqual(store.migration, { from: 2, to: SCHEMA_VERSION, newer: false });
  assert.equal(store.inbox("b").length, 1);
  store.close();
  const check = new DatabaseSync(path, { readOnly: true });
  const names = (check.prepare("PRAGMA table_info(messages)").all() as Array<{ name: string; notnull: number }>);
  for (const column of DELIVERY_COLUMNS) {
    const found = names.find((row) => row.name === column);
    assert.ok(found, column);
    assert.equal(found.notnull, 0, column);
  }
  check.close();
});

test("an older process can still insert a message into a v3 mailbox", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-v3-old-"));
  const path = join(dir, "bridge.sqlite");
  new BridgeStore(path).close();
  const raw = new DatabaseSync(path);
  raw.prepare(
    "INSERT INTO messages (from_agent, to_agent, body, thread_id, idempotency_key, created_at) VALUES (?, ?, ?, NULL, NULL, ?)",
  ).run("old", "b", "from an older bridge", new Date().toISOString());
  const row = raw.prepare("SELECT delivery_state FROM messages WHERE from_agent = 'old'").get() as { delivery_state: unknown };
  assert.equal(row.delivery_state, null);
  raw.close();
});

// agent-relay identity-check: v5 records the host session an agent was registered from.
const HOST_COLUMNS = ["host_app", "host_session"];

// agent-relay idempotency: v4 adds the reply link. Real runtimes still hold v2 mailboxes, so the v2 → v4 path is
// tested on its own: one open migrates both steps after one pre-migration backup.
function v2Mailbox(path: string): void {
  const fresh = new BridgeStore(path);
  fresh.register("a");
  fresh.register("b");
  fresh.send({ fromAgent: "a", toAgent: "b", body: "unread", idempotencyKey: "k1" });
  const handled = fresh.send({ fromAgent: "b", toAgent: "a", body: "handled" });
  fresh.ack("a", [handled.id]);
  fresh.close();
  const raw = new DatabaseSync(path);
  raw.exec("DROP INDEX idx_messages_delivery");
  raw.exec("DROP INDEX idx_messages_reply");
  for (const column of [...DELIVERY_COLUMNS, "reply_to"]) raw.exec(`ALTER TABLE messages DROP COLUMN ${column}`);
  for (const column of HOST_COLUMNS) raw.exec(`ALTER TABLE agents DROP COLUMN ${column}`);
  raw.exec("PRAGMA user_version = 2");
  raw.close();
}

test("a v2 mailbox migrates straight to the current schema in one open, after one backup, with its rows", () => {
  assert.equal(SCHEMA_VERSION, 5);
  const dir = mkdtempSync(join(tmpdir(), "bridge-v2-v4-"));
  const path = join(dir, "bridge.sqlite");
  const backupDir = join(dir, "backups");
  v2Mailbox(path);

  const store = new BridgeStore(path, { backupDir });
  assert.deepEqual(store.migration, { from: 2, to: 5, newer: false });
  const backups = readdirSync(backupDir);
  assert.equal(backups.length, 1);
  assert.match(backups[0] ?? "", /^bridge-pre-v5-from-v2-/);
  const copy = new DatabaseSync(join(backupDir, backups[0] as string), { readOnly: true });
  assert.equal((copy.prepare("PRAGMA user_version").get() as { user_version: number }).user_version, 2);
  assert.equal((copy.prepare("SELECT COUNT(*) AS n FROM messages").get() as { n: number }).n, 2);
  assert.equal((copy.prepare("SELECT COUNT(*) AS n FROM acknowledgements").get() as { n: number }).n, 1);
  copy.close();
  assert.deepEqual(store.inbox("b").map((message) => message.body), ["unread"]);
  assert.deepEqual(store.inbox("a").map((message) => message.body), []);
  assert.equal(store.deliver({ fromAgent: "a", toAgent: "b", body: "unread", idempotencyKey: "k1" }).duplicate, true);
  store.close();

  const check = new DatabaseSync(path, { readOnly: true });
  const names = check.prepare("PRAGMA table_info(messages)").all() as Array<{ name: string; notnull: number }>;
  for (const column of [...DELIVERY_COLUMNS, "reply_to"]) {
    assert.equal(names.find((row) => row.name === column)?.notnull, 0, column);
  }
  const agentColumns = check.prepare("PRAGMA table_info(agents)").all() as Array<{ name: string; notnull: number }>;
  for (const column of HOST_COLUMNS) assert.equal(agentColumns.find((row) => row.name === column)?.notnull, 0, column);
  check.close();
});

test("an older process can still insert a message into a v4 mailbox; its reply link reads as none", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-v4-old-"));
  const path = join(dir, "bridge.sqlite");
  new BridgeStore(path).close();
  const raw = new DatabaseSync(path);
  raw.prepare(
    "INSERT INTO messages (from_agent, to_agent, body, thread_id, idempotency_key, created_at) VALUES (?, ?, ?, NULL, NULL, ?)",
  ).run("old", "b", "from an older bridge", new Date().toISOString());
  raw.close();
  const store = new BridgeStore(path);
  assert.equal(store.inbox("b")[0]?.replyTo, null);
  store.close();
});

test("an older process can still register an agent in a v5 mailbox; it has no recorded host", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-v5-old-"));
  const path = join(dir, "bridge.sqlite");
  new BridgeStore(path).close();
  const raw = new DatabaseSync(path);
  const now = new Date().toISOString();
  raw.prepare("INSERT INTO agents (name, capabilities, registered_at, last_seen) VALUES (?, ?, ?, ?)").run("old", "[]", now, now);
  raw.close();
  const store = new BridgeStore(path);
  assert.equal(store.getAgent("old")?.host, null);
  store.close();
});

test("registration records the host it came from; a registration without one keeps it", () => {
  const store = new BridgeStore(":memory:");
  assert.equal(store.register("a").host, null);
  assert.deepEqual(store.register("a", undefined, { app: "claude", sessionId: "s-1" }).host, { app: "claude", sessionId: "s-1" });
  assert.deepEqual(store.register("a", ["review"]).host, { app: "claude", sessionId: "s-1" });
  assert.deepEqual(store.register("a", undefined, { app: "codex", sessionId: "t-1" }).host, { app: "codex", sessionId: "t-1" });
  store.close();
});

// agent-relay orchestrator-removal D93: the orchestration tables stay in the schema, unread, with their rows.
test("a v5 mailbox holding orchestration rows opens unchanged after the orchestrator was removed", () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-dormant-runs-"));
  const path = join(dir, "bridge.sqlite");
  new BridgeStore(path).close();
  const writer = new DatabaseSync(path);
  const now = new Date().toISOString();
  writer.prepare(`INSERT INTO orchestration_runs (id, coordinator_agent, project_path, worktree_path, thread_id, task,
    status, round, max_rounds, codex_session_id, latest_response, created_at, updated_at)
    VALUES ('kept-run', 'claude-main', '/repo', '/repo', 't', 'task', 'completed', 2, 6, NULL, NULL, ?, ?)`).run(now, now);
  writer.prepare("INSERT INTO orchestration_events (run_id, event_type, payload, created_at) VALUES ('kept-run', 'done', '{}', ?)")
    .run(now);
  writer.close();

  const store = new BridgeStore(path);
  assert.deepEqual(store.migration, { from: SCHEMA_VERSION, to: SCHEMA_VERSION, newer: false });
  store.close();
  const reader = new DatabaseSync(path, { readOnly: true });
  assert.equal(schemaVersion(reader), SCHEMA_VERSION);
  assert.deepEqual(
    { ...(reader.prepare("SELECT id, status, round FROM orchestration_runs").get() as object) },
    { id: "kept-run", status: "completed", round: 2 },
  );
  assert.equal((reader.prepare("SELECT COUNT(*) AS n FROM orchestration_events").get() as { n: number }).n, 1);
  reader.close();
});
