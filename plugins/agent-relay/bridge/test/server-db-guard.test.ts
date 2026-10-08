import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, statSync, utimesSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { BridgeStore } from "../src/bridge-store.js";
import { defaultDbPath } from "../src/paths.js";

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));

/** Start the server from source with a private HOME and data home, stdin closed, and BRIDGE_DB_PATH only if given. */
function startServer(home: string, dbPath?: string) {
  const env: NodeJS.ProcessEnv = { PATH: process.env.PATH ?? "", HOME: home, XDG_DATA_HOME: join(home, "data"), BRIDGE_BACKUPS: "0" };
  if (dbPath !== undefined) env.BRIDGE_DB_PATH = dbPath;
  return spawnSync(process.execPath, ["--import", "tsx", "src/server.ts"], {
    cwd: projectRoot, env, input: "", encoding: "utf8", timeout: 20_000,
  });
}

// agent-relay server-db-guard D114: the server never falls back to the upstream default database.
test("the server without BRIDGE_DB_PATH refuses to start and leaves an existing default database untouched", () => {
  const home = mkdtempSync(join(tmpdir(), "agent-relay-server-"));
  const fallback = defaultDbPath({ XDG_DATA_HOME: join(home, "data") }, home);
  mkdirSync(dirname(fallback), { recursive: true });
  const store = new BridgeStore(fallback);
  store.register("planted");
  store.close();
  const bytes = readFileSync(fallback);
  const past = new Date("2026-09-01T00:00:00Z");
  utimesSync(fallback, past, past);
  const before = readdirSync(dirname(fallback)).sort();

  const result = startServer(home);
  assert.equal(result.signal, null, "the server exits on its own");
  assert.equal(result.status, 2, result.stderr);
  assert.match(result.stderr, /\[agent-relay\] BRIDGE_DB_PATH is not set/);
  assert.match(result.stderr, /native_collaboration_adapters\.py install-claude \/ install-codex/);
  assert.equal(result.stdout, "");
  assert.deepEqual(readFileSync(fallback), bytes, "the default database's bytes are unchanged");
  assert.equal(statSync(fallback).mtimeMs, past.getTime(), "the default database's mtime is unchanged");
  assert.deepEqual(readdirSync(dirname(fallback)).sort(), before, "no -wal, -shm or backup file appeared");
});

test("the server without BRIDGE_DB_PATH, or with a blank one, creates nothing", () => {
  for (const dbPath of [undefined, "  "]) {
    const home = mkdtempSync(join(tmpdir(), "agent-relay-server-"));
    const result = startServer(home, dbPath);
    assert.equal(result.signal, null, "the server exits on its own");
    assert.equal(result.status, 2, result.stderr);
    assert.match(result.stderr, /BRIDGE_DB_PATH is not set/);
    assert.deepEqual(readdirSync(home), [], `nothing created under HOME (BRIDGE_DB_PATH=${JSON.stringify(dbPath)})`);
  }
});
