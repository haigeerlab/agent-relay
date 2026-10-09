// agent-relay long-messages (D150-D153): a long message costs the sender nothing and is read in parts, by tools alone.
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { session } from "./support/session.js";

/** About 160 000 UTF-8 bytes of Chinese text with numbered lines, so order and completeness can be checked. */
function longChinese(): string {
  const lines: string[] = [];
  let bytes = 0;
  for (let i = 0; bytes < 160_000; i++) {
    const line = `第${i}行：长消息分段读取的测试内容，包含中文与标点。\n`;
    lines.push(line);
    bytes += Buffer.byteLength(line);
  }
  return lines.join("");
}

test("bridge_send returns no body, only its length, even for a 160 000-byte message (D150)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-long-send-"));
  const body = longChinese();
  const path = join(dir, "long.txt");
  writeFileSync(path, body);
  const a = await session(dir, "claude-long-a");
  try {
    await a.call("bridge_register", { agent: "alice" });
    await a.call("bridge_register", { agent: "bob" });
    for (const attempt of ["first", "duplicate"]) {
      const sent = await a.call("bridge_send", { from: "alice", to: "bob", bodyFile: path, idempotencyKey: "long-1" });
      assert.ok(sent.ok, sent.text.slice(0, 500));
      const result = sent.json();
      assert.equal("body" in result, false, attempt);
      assert.equal(result.bodyLength, body.length, attempt);
      assert.ok(sent.text.length < 2_000, `${attempt}: ${sent.text.length} characters`);
      assert.equal(typeof result.id, "number");
    }
  } finally {
    await a.close();
  }
});

test("page budgets count other scripts as about one token per character (D151)", async () => {
  const { fitMessages, textCost, DEFAULT_PAGE_CHARS } = await import("../src/paging.js");
  const message = (id: number, body: string) => ({ id, fromAgent: "a", toAgent: "b", body, threadId: null,
    replyTo: null, createdAt: "2026-10-09T00:00:00.000Z", deliveryState: "queued" as const }) as any;
  assert.equal(textCost("abc"), 3);
  assert.equal(textCost("中文"), 8);
  assert.equal(textCost("🙂"), 4, "one code point, not two");

  const english = fitMessages([message(1, "x".repeat(60_000))]);
  assert.equal(english.messages[0].body.length, DEFAULT_PAGE_CHARS - 320, "English pages are unchanged");

  const chinese = fitMessages([message(1, "中".repeat(60_000))]);
  assert.equal(chinese.messages[0].bodyTruncated, true);
  assert.ok(textCost(chinese.messages[0].body) <= DEFAULT_PAGE_CHARS - 320);
  assert.ok(chinese.messages[0].body.length >= 11_000, `${chinese.messages[0].body.length} characters`);

  const several = fitMessages([1, 2, 3, 4, 5].map((id) => message(id, "文".repeat(5_000))));
  assert.equal(several.messages.length, 2);
  assert.equal(several.omitted, 3);

  const emoji = fitMessages([message(1, "🙂".repeat(20_000))]).messages[0].body;
  const last = emoji.charCodeAt(emoji.length - 1);
  assert.ok(!(last >= 0xd800 && last <= 0xdbff), "never ends inside a surrogate pair");
  assert.equal(emoji.length % 2, 0);
});
