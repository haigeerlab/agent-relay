// agent-relay identity-check (assumption 6, D38): an auto-approved Codex session is not bound or pinged.
import assert from "node:assert/strict";
import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BridgeStore } from "../src/bridge-store.js";
import { codexApproval } from "../src/codex-approval.js";
import { sweepDeliveryFailures } from "../src/notices.js";
import { WakeDispatcher } from "../src/wake-dispatcher.js";
import { session } from "./support/session.js";

function codexHome(config: string | null): string {
  const home = mkdtempSync(join(tmpdir(), "agent-relay-codex-home-"));
  if (config !== null) writeFileSync(join(home, "config.toml"), config);
  return home;
}

test("guardian review, approval_policy never, unreadable and malformed configs count as auto-approved", () => {
  const cases: Array<[string, string | null, boolean]> = [
    ["guardian", 'approval_policy = "on-request"\napprovals_reviewer = "guardian_subagent"\n', true],
    ["never", "approval_policy = 'never'  # full auto\n", true],
    ["on-request", 'approval_policy = "on-request"\nsandbox_mode = "workspace-write"\n', false],
    ["missing file (Codex defaults)", null, false],
    ["unquoted value", "approvals_reviewer = guardian_subagent\n", true],
    ["profiles are not evaluated", 'approval_policy = "on-request"\n[profiles.fast]\napproval_policy = "never"\n', false],
    ["keys inside a table are not top level", '[mcp_servers.x]\napprovals_reviewer = "guardian_subagent"\n', false],
  ];
  for (const [name, config, auto] of cases) {
    const result = codexApproval({ CODEX_HOME: codexHome(config) });
    assert.equal(result.autoApproved, auto, `${name}: ${result.reason}`);
    assert.ok(result.reason.length > 0, name);
  }
  if (process.getuid?.() !== 0) {
    const home = codexHome('approval_policy = "on-request"\n');
    chmodSync(join(home, "config.toml"), 0o000);
    const unreadable = codexApproval({ CODEX_HOME: home });
    assert.equal(unreadable.autoApproved, true);
    assert.match(unreadable.reason, /could not be read/);
  }
  const guardian = codexApproval({ CODEX_HOME: codexHome('approvals_reviewer = "guardian_subagent"\n') });
  assert.match(guardian.reason, /approvals_reviewer = "guardian_subagent"/);
});

test("without CODEX_HOME the config is read from ~/.codex", () => {
  const home = mkdtempSync(join(tmpdir(), "agent-relay-home-"));
  mkdirSync(join(home, ".codex"));
  writeFileSync(join(home, ".codex", "config.toml"), 'approval_policy = "never"\n');
  assert.equal(codexApproval({ HOME: home }).autoApproved, true);
});

test("a Codex wake binding is refused under auto-approval; registering without wake still works", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-codex-bind-"));
  const codex = await session(dir, null, { CODEX_HOME: codexHome('approvals_reviewer = "guardian_subagent"\n') });
  try {
    const bound = await codex.call("bridge_register", { agent: "carol", wake: { app: "codex", sessionId: "thread-1" } });
    assert.equal(bound.ok, false);
    assert.match(bound.text, /auto-approv/);
    assert.match(bound.text, /请求批准/);
    assert.ok((await codex.call("bridge_register", { agent: "carol" })).ok);
  } finally {
    await codex.close();
  }
});

test("a ping to a bound Codex session is held, not sent, while its config is auto-approved", async () => {
  const store = new BridgeStore(":memory:");
  store.register("s");
  store.register("c");
  store.wakes.bind("c", { app: "codex", sessionId: "thread-c" });
  const message = store.send({ fromAgent: "s", toAgent: "c", body: "work" });
  const dispatcher = new WakeDispatcher(store, { env: { CODEX_HOME: codexHome('approval_policy = "never"\n') } });
  await dispatcher.flush();
  const job = store.wakes.forMessage(message.id);
  assert.equal(job?.state, "held");
  assert.match(job?.detail ?? "", /auto-approv/);
  assert.equal(store.wakes.target("c")?.sessionId, "thread-c", "the binding is kept");
  assert.equal(sweepDeliveryFailures(store), 1);
  const notice = store.inbox("s").find((m) => m.fromAgent === "bridge");
  assert.match(notice?.body ?? "", /held by the bridge because the recipient's Codex runs with auto-approval/);
  await dispatcher.close();
  store.close();
});
