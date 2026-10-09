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
