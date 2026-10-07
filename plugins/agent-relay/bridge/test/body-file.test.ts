// agent-relay ops-commands (D43): a message body read from a file arrives byte-identical.
import assert from "node:assert/strict";
import { mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { BodyFileError, MAX_BODY_FILE_BYTES, readBodyFile } from "../src/body-file.js";
import { session } from "./support/session.js";

const TRICKY = "rm -rf $HOME; echo `id` && $(whoami) | 'quoted' \"double\" \\back\r\nCRLF line\n\ttab * ? [x] ~ ! # 中文 🙂\uFEFF no trailing newline";

function file(dir: string, name: string, content: string | Buffer): string {
  const path = join(dir, name);
  writeFileSync(path, content);
  return path;
}

test("a text file is read exactly, including shell metacharacters, CRLF, a BOM and no trailing newline", () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-body-"));
  assert.equal(readBodyFile(file(dir, "tricky.txt", TRICKY)), TRICKY);
  const bom = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from("starts with a BOM")]);
  assert.deepEqual(Buffer.from(readBodyFile(file(dir, "bom.txt", bom)), "utf8"), bom);
});

test("relative paths, missing files, symlinks, directories, empty, oversized and non-UTF-8 files are refused", () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-body-bad-"));
  const target = file(dir, "real.txt", "real");
  symlinkSync(target, join(dir, "link.txt"));
  const cases: Array<[string, string, RegExp]> = [
    ["relative", "real.txt", /absolute path/],
    ["missing", join(dir, "nope.txt"), /does not exist/],
    ["symlink", join(dir, "link.txt"), /symbolic link/],
    ["directory", dir, /regular file/],
    ["empty", file(dir, "empty.txt", ""), /empty/],
    ["oversized", file(dir, "big.txt", Buffer.alloc(MAX_BODY_FILE_BYTES + 1, 0x61)), /256 KiB/],
    ["not UTF-8", file(dir, "latin1.txt", Buffer.from([0x63, 0x61, 0x66, 0xe9])), /UTF-8/],
  ];
  for (const [name, path, message] of cases) {
    assert.throws(() => readBodyFile(path), (error: unknown) => error instanceof BodyFileError && message.test((error as Error).message), name);
  }
  assert.equal(readBodyFile(file(dir, "max.txt", Buffer.alloc(MAX_BODY_FILE_BYTES, 0x61))).length, MAX_BODY_FILE_BYTES);
});

test("bridge_send takes exactly one of body and bodyFile and stores the file's text unchanged", async () => {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-body-mcp-"));
  const path = file(dir, "body.txt", TRICKY);
  const a = await session(dir, "claude-session-a");
  try {
    await a.call("bridge_register", { agent: "alice" });
    await a.call("bridge_register", { agent: "bob" });
    const sent = await a.call("bridge_send", { from: "alice", to: "bob", bodyFile: path });
    assert.ok(sent.ok, sent.text);
    const inbox = (await a.call("bridge_inbox", { agent: "bob" })).json();
    assert.equal(inbox.messages[0].body, TRICKY);
    assert.match((await a.call("bridge_send", { from: "alice", to: "bob", body: "x", bodyFile: path })).text, /exactly one of body and bodyFile/);
    assert.match((await a.call("bridge_send", { from: "alice", to: "bob" })).text, /exactly one of body and bodyFile/);
    assert.match((await a.call("bridge_send", { from: "alice", to: "bob", bodyFile: "body.txt" })).text, /absolute path/);
  } finally {
    await a.close();
  }
});
