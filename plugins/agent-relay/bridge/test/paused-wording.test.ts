import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { checkRecipient } from "../src/addressing.js";
import { BridgeStore } from "../src/bridge-store.js";
import { claudeNotRunning } from "../src/claude-wake.js";
import { claudeOfflineExplanation } from "../src/notices.js";
import { noticeText } from "../src/notify.js";

const link = "claude://claude.ai/epitaxy/local_00000000-0000-4000-8000-000000000001";
const d289 = 'The Claude app paused this session or it was closed; it reads its mailbox only after it is opened. Tell the user: "Open the Claude session \'Review\' (mailbox name recipient) so it can read its waiting messages."';
const d291 = "If the user asks to wake it now and you are a Claude session in the desktop app, you may send it one line with the app's session message tool to session local_00000000-0000-4000-8000-000000000001, asking it to read its mailbox. Do not do this unasked or repeatedly; the app may pause another session to make room.";

test("paused-session-link D289 and D291 name linked sessions only where a sender reads the text", async () => {
  const store = new BridgeStore(join(mkdtempSync(join(tmpdir(), "ar-paused-wording-")), "bridge.sqlite"));
  store.register("recipient", [], { app: "claude", sessionId: "stopped" }, { link, title: "Review" });
  const warning = await checkRecipient(store, "recipient", { presenceOf: async () => ({ state: "stopped" }) });
  assert.equal(warning.warnings[0], '"recipient"\'s Claude session is not running. The message will wait in its inbox until that conversation reads it. ' + d289 + " " + d291);
  assert.equal(claudeNotRunning("recipient", store.getAgent("recipient")?.desktop),
    "Claude session is not running; the message waits and is delivered once that session is opened. " + d289);
  assert.equal(claudeOfflineExplanation("recipient", store.getAgent("recipient")?.desktop),
    "The recipient's Claude session was not running for the whole one-hour retry window (the Claude app may stop idle sessions). The message stays in its inbox and is delivered once that session is opened. " + d289 + " " + d291);
  const notification = noticeText({ kind: "offline", messageId: 1, fromAgent: "sender", agent: "recipient", why: "offline", since: 0,
    desktop: store.getAgent("recipient")?.desktop });
  assert.ok(notification.endsWith("The Claude app paused this session or it was closed. Open the Claude session 'Review' (mailbox name recipient) to deliver them."), notification);
  assert.doesNotMatch(notification, /Tell the user/);
  assert.doesNotMatch(notification, /If the user asks to wake it now/);
  store.close();
});

test("paused-session-link D289 omits title and D291 without a desktop link", () => {
  const text = claudeNotRunning("recipient");
  assert.ok(text.includes('"Open the Claude session recipient so it can read its waiting messages."'));
  assert.doesNotMatch(text, /If the user asks to wake it now/);
});
