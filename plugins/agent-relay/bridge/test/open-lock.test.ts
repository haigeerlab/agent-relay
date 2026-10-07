// agent-relay identity-check (D40): opening the mailbox waits for another process's lock instead of failing at once.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";

test("a process opens, reads and writes the mailbox while another holds the lock briefly", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-open-lock-"));
  const path = join(dir, "bridge.sqlite");
  const setup = new BridgeStore(path);
  setup.send({ fromAgent: "a", toAgent: "b", body: "before" });
  setup.close();

  // The holder takes an exclusive lock, says so, keeps it for 800 ms, then releases it.
  const holder = spawn(process.execPath, ["--input-type=module", "-e", `
    import { DatabaseSync } from "node:sqlite";
    const db = new DatabaseSync(${JSON.stringify(path)});
    db.exec("PRAGMA locking_mode = EXCLUSIVE; BEGIN EXCLUSIVE");
    db.prepare("SELECT COUNT(*) FROM messages").get();
    console.log("locked");
    setTimeout(() => { db.exec("COMMIT"); db.close(); }, 800);
  `]);
  await new Promise<void>((resolve, reject) => {
    holder.stdout.on("data", (chunk) => { if (String(chunk).includes("locked")) resolve(); });
    holder.on("close", (code) => reject(new Error(`holder exited ${code}`)));
  });

  const started = Date.now();
  const store = new BridgeStore(path);
  assert.deepEqual(store.inbox("b").map((m) => m.body), ["before"]);
  store.send({ fromAgent: "a", toAgent: "b", body: "after" });
  assert.equal(store.inbox("b").length, 2);
  store.close();
  assert.ok(Date.now() - started >= 500, "it waited for the lock");
  await new Promise((resolve) => holder.on("close", resolve));
});
