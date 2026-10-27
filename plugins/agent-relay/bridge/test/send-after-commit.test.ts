// agent-relay delivery-robustness D261: once bridge_send has committed the message, a later step that fails (the
// database busy while it records the sender or dispatches the ping) returns the stored message with a warning, so an
// error from bridge_send always means nothing was stored.
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import type { Presence } from "../src/presence.js";
import { type SendContext, sendMessage } from "../src/send.js";
import { CLAUDE_HOLD_GRACE_MS, sweepDeliveryFailures } from "../src/notices.js";
import { LATE_RECEIPT_RETRY_MS, WakeDispatcher } from "../src/wake-dispatcher.js";

function setup() {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-after-commit-"));
  const dbPath = join(dir, "bridge.sqlite");
  const store = new BridgeStore(dbPath);
  store.register("sender");
  store.register("recipient");
  store.wakes.bind("recipient", { app: "codex", sessionId: "recipient-task" });
  const env = { AGENT_RELAY_NOTIFY_LOG: join(dir, "notices.log") } as NodeJS.ProcessEnv;
  const dispatcher = new WakeDispatcher(store, {
    env, codexWake: async () => ({ state: "accepted", detail: "Codex accepted the ping" }),
  });
  const context = (flush: () => Promise<void>): SendContext => ({
    dbPath, flush, presenceOf: async () => ({ state: "unknown" }) as unknown as Presence,
  });
  /** Hold the database's write lock from a second connection while `step` runs. */
  const whileLocked = async <T>(step: () => Promise<T> | T): Promise<T> => {
    const other = new DatabaseSync(dbPath);
    other.exec("BEGIN IMMEDIATE");
    store.database.exec("PRAGMA busy_timeout = 50");
    try {
      return await step();
    } finally {
      other.exec("ROLLBACK");
      other.close();
      store.database.exec("PRAGMA busy_timeout = 5000");
    }
  };
  const stored = () => store.database.prepare("SELECT id, body FROM messages WHERE from_agent = 'sender'").all();
  return { store, dispatcher, context, whileLocked, stored };
}

const request = { from: "sender", to: "recipient", body: "please review" };

test("a dispatch that fails after the commit returns the stored message and a do-not-resend warning", async () => {
  const { store, context, stored } = setup();
  const result = await sendMessage(store, request, context(async () => { throw new Error("database is locked"); }));
  assert.equal(stored().length, 1);
  assert.equal(result.id, Number(stored()[0]!.id));
  assert.ok(result.warnings?.some((warning) =>
    warning.includes(`Saved as #${result.id}`) && /busy/.test(warning) && /Do not send it again/.test(warning)));
  store.close();
});

test("a failure that is not a busy database is named in the warning", async () => {
  const { store, context } = setup();
  const result = await sendMessage(store, request, context(async () => { throw new Error("disk I/O error"); }));
  assert.ok(result.warnings?.some((warning) => /disk I\/O error/.test(warning) && /Do not send it again/.test(warning)));
  store.close();
});

test("recording the sender's activity failing after the commit does not fail the send", async () => {
  const { store, context, stored } = setup();
  store.touch = () => { throw new Error("database is locked"); };
  const result = await sendMessage(store, request, context(async () => {}));
  assert.equal(stored().length, 1);
  assert.ok(result.warnings?.some((warning) => warning.includes(`Saved as #${result.id}`)));
  store.close();
});

test("the database locked by another process during the dispatch does not fail the send", async () => {
  const { store, dispatcher, context, whileLocked, stored } = setup();
  const result = await sendMessage(store, request, context(() => whileLocked(() => dispatcher.flush())));
  assert.equal(stored().length, 1);
  assert.equal(result.id, Number(stored()[0]!.id));
  // The ping is still due, so the next dispatch sends it.
  await dispatcher.flush();
  assert.equal(store.wakes.forMessage(result.id)?.state, "accepted");
  store.close();
});

test("the dispatcher's flush resolves when claiming or finishing a ping throws", async () => {
  const { store, dispatcher } = setup();
  store.send({ fromAgent: "sender", toAgent: "recipient", body: "one" });
  const finish = store.wakes.finish.bind(store.wakes);
  store.wakes.finish = () => { throw new Error("database is locked"); };
  await dispatcher.flush();
  store.wakes.finish = finish;
  const claim = store.wakes.claim.bind(store.wakes);
  store.wakes.claim = () => { throw new Error("database is locked"); };
  await dispatcher.flush();
  store.wakes.claim = claim;
  store.close();
});

test("a refusal before the commit still fails the send and stores nothing", async () => {
  const { store, context, stored } = setup();
  await assert.rejects(sendMessage(store, { ...request, to: "nobody" }, context(async () => {})));
  assert.equal(stored().length, 0);
  store.close();
});

// Review of #164: a ping whose result could not be written is never sent again (S47).
test("a ping whose finish failed is recorded unknown after 30 seconds and not sent again", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-after-commit-"));
  const store = new BridgeStore(join(dir, "bridge.sqlite"));
  store.register("sender");
  store.register("recipient");
  store.wakes.bind("recipient", { app: "codex", sessionId: "recipient-task" });
  let pings = 0;
  const dispatcher = new WakeDispatcher(store, {
    env: { AGENT_RELAY_NOTIFY_LOG: join(dir, "notices.log") } as NodeJS.ProcessEnv,
    codexWake: async () => { pings += 1; return { state: "accepted", detail: "Codex accepted the ping" }; },
  });
  const message = store.send({ fromAgent: "sender", toAgent: "recipient", body: "one" });
  const finish = store.wakes.finish.bind(store.wakes);
  store.wakes.finish = () => { throw new Error("database is locked"); };
  await dispatcher.flush();
  store.wakes.finish = finish;
  assert.equal(store.wakes.forMessage(message.id)?.state, "sending");
  assert.equal(store.wakes.claim(Date.now() + 31_000), null);
  assert.equal(store.wakes.forMessage(message.id)?.state, "unknown");
  await dispatcher.flush();
  assert.equal(pings, 1, "the adapter was called once");
  await dispatcher.close();
  store.close();
});

// Review of #164 (D267): a late "released" receipt that meets a busy database is written on a later try, so the hold is
// not announced as one that lasted.
test("a late Claude receipt whose write met a busy database is written on a later try", async () => {
  const { store, dispatcher, whileLocked } = setup();
  store.wakes.bind("recipient", { app: "claude", sessionId: "recipient-session" }, { replace: true });
  const message = store.send({ fromAgent: "sender", toAgent: "recipient", body: "please review" });
  const job = store.wakes.claim()!;
  store.wakes.finish(job, { state: "held", detail: "held" });
  await whileLocked(() => dispatcher.lateReceipt(job, { state: "accepted", detail: "Claude confirmed peer delivery" }));
  assert.equal(store.wakes.forMessage(message.id)?.state, "held");
  await new Promise((resolve) => setTimeout(resolve, LATE_RECEIPT_RETRY_MS + 500));
  assert.equal(store.wakes.forMessage(message.id)?.state, "accepted");
  assert.equal(sweepDeliveryFailures(store, Date.now() + 10 * CLAUDE_HOLD_GRACE_MS), 0);
  await dispatcher.close();
  store.close();
});
