import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, statSync, utimesSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { BridgeStore } from "../src/bridge-store.js";
import { parseCliCommand } from "../src/cli-logic.js";
import { defaultDbPath } from "../src/paths.js";
import { VERSION } from "../src/version.js";

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));

/** Run the CLI from source against a private mailbox and HOME, as the Python retire script runs the built one. */
function cli(args: string[], dbPath: string) {
  const home = dirname(dbPath);
  return spawnSync(process.execPath, ["--import", "tsx", "src/cli.ts", ...args], {
    cwd: projectRoot,
    env: { PATH: process.env.PATH ?? "", HOME: home, BRIDGE_DB_PATH: dbPath, XDG_DATA_HOME: join(home, "data") },
    encoding: "utf8",
  });
}

// agent-relay legacy-cli-cleanup D95: installing, upgrading, checking and uninstalling belong to the Python runtime.
test("the CLI parses only retire and help", () => {
  const retire = parseCliCommand(["retire", "opus-worker", "--note", "task merged", "--keep-backlog"]);
  assert.deepEqual([retire.command, retire.target, retire.note, retire.keepBacklog], ["retire", "opus-worker", "task merged", true]);
  assert.equal(parseCliCommand(["retire", "x", "--note=done"]).note, "done");
  assert.equal(parseCliCommand(["-h"]).command, "help");
  assert.equal(parseCliCommand([]).command, "help");
  for (const removed of ["setup", "doctor", "status", "demo", "prune", "backup", "rollback", "uninstall"]) {
    assert.throws(() => parseCliCommand([removed]), /Unknown command/, removed);
  }
  assert.throws(() => parseCliCommand(["retire"]), /needs an agent/);
  assert.throws(() => parseCliCommand(["retire", "x", "--purge"]), /Unknown option/);
  assert.throws(() => parseCliCommand(["retire", "x", "extra"]), /Unexpected argument/);
});

test("an unknown command prints the usage and exits 2", () => {
  const dbPath = join(mkdtempSync(join(tmpdir(), "agent-relay-cli-")), "bridge.sqlite");
  const result = cli(["bogus"], dbPath);
  assert.equal(result.status, 2, result.stderr);
  assert.match(result.stderr, /Unknown command: bogus/);
  assert.match(result.stderr, /retire <agent> \[--note TEXT\] \[--keep-backlog\]/);
});

test("help names the package and points to the Python runtime", () => {
  const dbPath = join(mkdtempSync(join(tmpdir(), "agent-relay-cli-")), "bridge.sqlite");
  const result = cli(["help"], dbPath);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /^agent-relay-bridge \d+\.\d+\.\d+\n/);
  assert.match(result.stdout, /\n {2}agent-relay-bridge <command> \[options\]\n/);
  assert.match(result.stdout, /native_collaboration_runtime\.py/);
  assert.doesNotMatch(result.stdout, /claude-codex/i);
});

test("the package is agent-relay-bridge with one bin for the CLI", () => {
  const manifest = JSON.parse(readFileSync(join(projectRoot, "package.json"), "utf8")) as { name: string; bin: Record<string, string> };
  const lock = JSON.parse(readFileSync(join(projectRoot, "package-lock.json"), "utf8")) as { name: string; packages: Record<string, { name?: string }> };
  assert.equal(manifest.name, "agent-relay-bridge");
  assert.deepEqual(manifest.bin, { "agent-relay-bridge": "dist/cli.js" });
  assert.equal(lock.name, "agent-relay-bridge");
  assert.equal(lock.packages[""]?.name, "agent-relay-bridge");
});

test("retire through the CLI keeps its output, exit code and --keep-backlog", () => {
  const dbPath = join(mkdtempSync(join(tmpdir(), "agent-relay-cli-")), "bridge.sqlite");
  const store = new BridgeStore(dbPath);
  store.register("lead");
  store.register("kept");
  store.register("closed");
  store.send({ fromAgent: "lead", toAgent: "kept", body: "one", wake: false });
  store.send({ fromAgent: "lead", toAgent: "closed", body: "two", wake: false });
  store.close();

  const kept = cli(["retire", "kept", "--keep-backlog", "--note", "done"], dbPath);
  assert.equal(kept.status, 0, kept.stderr);
  assert.match(kept.stdout, /^✓ Retired kept\n {2}Closed 0 unhandled message\(s\)/);
  const closed = cli(["retire", "closed"], dbPath);
  assert.equal(closed.status, 0, closed.stderr);
  assert.match(closed.stdout, /Closed 1 unhandled message\(s\)/);
  const missing = cli(["retire", "nobody"], dbPath);
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /^✗ /);

  const after = new BridgeStore(dbPath);
  assert.equal(after.inbox("kept").length, 1, "--keep-backlog leaves the message unhandled");
  assert.equal(after.inbox("closed").length, 0);
  assert.equal(after.getAgent("kept")?.retiredBy, "operator");
  after.close();
});

/** Run the CLI from source with a private HOME and data home but no BRIDGE_DB_PATH, unless `dbPath` is given. */
function cliWithoutDb(args: string[], home: string, dbPath?: string) {
  const env: NodeJS.ProcessEnv = { PATH: process.env.PATH ?? "", HOME: home, XDG_DATA_HOME: join(home, "data") };
  if (dbPath !== undefined) env.BRIDGE_DB_PATH = dbPath;
  return spawnSync(process.execPath, ["--import", "tsx", "src/cli.ts", ...args], { cwd: projectRoot, env, encoding: "utf8" });
}

// agent-relay retire-cli-guard D111: retire never falls back to the upstream default database.
test("retire without BRIDGE_DB_PATH refuses and leaves an existing default database untouched", () => {
  const home = mkdtempSync(join(tmpdir(), "agent-relay-cli-"));
  const fallback = defaultDbPath({ XDG_DATA_HOME: join(home, "data") }, home);
  mkdirSync(dirname(fallback), { recursive: true });
  const store = new BridgeStore(fallback);
  store.register("planted");
  store.close();
  const bytes = readFileSync(fallback);
  const past = new Date("2026-09-01T00:00:00Z");
  utimesSync(fallback, past, past);
  const before = readdirSync(dirname(fallback)).sort();

  const result = cliWithoutDb(["retire", "planted"], home);
  assert.equal(result.status, 2, result.stderr);
  assert.match(result.stderr, /BRIDGE_DB_PATH/);
  assert.match(result.stderr, /native_collaboration_retire\.py --name <agent> --confirm-retire/);
  assert.equal(result.stdout, "");
  assert.deepEqual(readFileSync(fallback), bytes, "the default database's bytes are unchanged");
  assert.equal(statSync(fallback).mtimeMs, past.getTime(), "the default database's mtime is unchanged");
  assert.deepEqual(readdirSync(dirname(fallback)).sort(), before, "no -wal or -shm file appeared");
  const after = new BridgeStore(fallback);
  assert.equal(after.getAgent("planted")?.retiredAt ?? null, null, "the agent is not retired");
  after.close();
});

test("retire without BRIDGE_DB_PATH, or with a blank one, creates nothing", () => {
  for (const dbPath of [undefined, "  "]) {
    const home = mkdtempSync(join(tmpdir(), "agent-relay-cli-"));
    const result = cliWithoutDb(["retire", "anyone"], home, dbPath);
    assert.equal(result.status, 2, result.stderr);
    assert.match(result.stderr, /native_collaboration_retire\.py/);
    assert.deepEqual(readdirSync(home), [], `nothing created under HOME (BRIDGE_DB_PATH=${JSON.stringify(dbPath)})`);
  }
});

test("help needs no BRIDGE_DB_PATH and says retire does", () => {
  const home = mkdtempSync(join(tmpdir(), "agent-relay-cli-"));
  const result = cliWithoutDb(["help"], home);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /needs BRIDGE_DB_PATH; run by native_collaboration_retire\.py/);
  assert.deepEqual(readdirSync(home), []);
});

test("paths honour overrides and default to the per-user data directory", () => {
  const home = "/Users/example";
  assert.equal(defaultDbPath({}, home), join(home, ".local", "share", "claude-codex-bridge", "bridge.sqlite"));
  assert.equal(defaultDbPath({ XDG_DATA_HOME: "/data" }, home), join("/data", "claude-codex-bridge", "bridge.sqlite"));
  assert.equal(defaultDbPath({ BRIDGE_DB_PATH: "/tmp/x.sqlite" }, home), "/tmp/x.sqlite");
});

test("the reported version matches package.json", () => {
  const manifest = JSON.parse(readFileSync(join(projectRoot, "package.json"), "utf8")) as { version: string };
  assert.equal(VERSION, manifest.version);
});
