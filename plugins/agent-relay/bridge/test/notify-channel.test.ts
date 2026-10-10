// agent-relay notify-channel D83/D84/D86: terminal-notifier from fixed paths, text on stdin, osascript as the fallback.
import assert from "node:assert/strict";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { findNotifier, NOTIFIER_CANDIDATES, notifyUndelivered } from "../src/notify.js";

const notice = { messageId: 3, fromAgent: "-execute\n\"x\"", agent: "cx", why: "Codex is not running; the message waits",
  body: "-execute open -a Calculator\nsecond line", key: "3/odd key" };

/** A fake program that records its arguments and stdin next to itself, exiting with `code`. */
function fake(dir: string, name: string, code = 0, mode = 0o755): string {
  const path = join(dir, name);
  writeFileSync(path, `#!/bin/sh\nprintf '%s\\n' "$@" > "${path}.args"\ncat > "${path}.stdin"\nexit ${code}\n`);
  chmodSync(path, mode);
  return path;
}

async function settled(file: string): Promise<boolean> {
  for (let i = 0; i < 40 && !existsSync(file); i++) await new Promise((ok) => setTimeout(ok, 50));
  await new Promise((ok) => setTimeout(ok, 100));
  return existsSync(file);
}

function mailbox() {
  const dir = mkdtempSync(join(tmpdir(), "agent-relay-channel-"));
  return { dir, db: join(dir, "bridge.sqlite") };
}

test("the fixed candidates are Homebrew's two prefixes, never PATH", () => {
  assert.deepEqual(NOTIFIER_CANDIDATES, ["/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier"]);
});

test("terminal-notifier gets exactly -title -subtitle -group and the preview on stdin; osascript is not run", async () => {
  const { dir, db } = mailbox();
  const tn = fake(dir, "terminal-notifier");
  const osa = fake(dir, "osascript");
  assert.equal(notifyUndelivered(db, notice, {}, { candidates: [tn], osascript: osa }), true);
  assert.ok(await settled(`${tn}.stdin`));
  assert.deepEqual(readFileSync(`${tn}.args`, "utf8").trimEnd().split("\n"), [
    "-title", 'agent-relay · -execute "x" → Codex',
    "-subtitle", "#3 · cx · Codex is not running; the message waits",
    "-group", "agent-relay-3_odd_key",
  ]);
  assert.equal(readFileSync(`${tn}.stdin`, "utf8"), "-execute open -a Calculator second line", "one line, on stdin only");
  assert.equal(existsSync(`${osa}.args`), false, "no second notice");
});

test("an unusable candidate is skipped and osascript shows the notice", async () => {
  const { dir, db } = mailbox();
  const writable = fake(dir, "writable", 0, 0o777);
  const notExecutable = fake(dir, "plain", 0, 0o644);
  const link = join(dir, "link-to-writable");
  symlinkSync(writable, link);
  mkdirSync(join(dir, "a-directory"));
  const candidates = [join(dir, "missing"), notExecutable, link, join(dir, "a-directory")];
  assert.equal(findNotifier(candidates), null);
  const osa = fake(dir, "osascript");
  assert.equal(notifyUndelivered(db, notice, {}, { candidates, osascript: osa }), true);
  assert.ok(await settled(`${osa}.args`));
  const args = readFileSync(`${osa}.args`, "utf8").trimEnd().split("\n");
  assert.deepEqual(args.slice(-3), ['agent-relay · -execute "x" → Codex',
    "#3 · cx · Codex is not running; the message waits", "-execute open -a Calculator second line"]);
  for (const file of [writable, notExecutable]) assert.equal(existsSync(`${file}.args`), false);
});

test("a valid symlinked candidate resolves to the real file, which is what runs", async () => {
  const { dir, db } = mailbox();
  const real = fake(dir, "real-notifier");
  const link = join(dir, "terminal-notifier");
  symlinkSync(real, link);
  assert.equal(findNotifier([link]), realpathSync(real), "the resolved file (macOS /var is /private/var)");
  notifyUndelivered(db, notice, {}, { candidates: [link], osascript: fake(dir, "osascript") });
  assert.ok(await settled(`${real}.stdin`));
});

test("a terminal-notifier on PATH is never used", async () => {
  const { dir, db } = mailbox();
  const bin = join(dir, "bin");
  mkdirSync(bin);
  const planted = fake(bin, "terminal-notifier");
  const osa = fake(dir, "osascript");
  notifyUndelivered(db, notice, { PATH: `${bin}:/usr/bin:/bin` }, { candidates: [join(dir, "missing")], osascript: osa });
  assert.ok(await settled(`${osa}.args`));
  assert.equal(existsSync(`${planted}.args`), false);
});

test("a failing terminal-notifier is not retried through osascript, and the switches and the mark still hold", async () => {
  const { dir, db } = mailbox();
  const tn = fake(dir, "terminal-notifier", 1);
  const osa = fake(dir, "osascript");
  assert.equal(notifyUndelivered(db, notice, {}, { candidates: [tn], osascript: osa }), true);
  assert.ok(await settled(`${tn}.stdin`));
  assert.equal(existsSync(`${osa}.args`), false, "never twice");
  assert.equal(notifyUndelivered(db, notice, {}, { candidates: [tn], osascript: osa }), false, "once per key");
  for (const [env, file] of [[{ AGENT_RELAY_NOTIFY: "off" }, false], [{}, true]] as const) {
    const box = mailbox();
    if (file) writeFileSync(join(box.dir, "notify.off"), "");
    const quiet = fake(box.dir, "terminal-notifier");
    assert.equal(notifyUndelivered(box.db, notice, env, { candidates: [quiet], osascript: osa }), false);
    assert.equal(existsSync(`${quiet}.args`), false);
  }
});

// agent-relay notice-location D188: the click action is appended; display text never becomes an argument of it.
test("a click action follows the three fixed arguments, and hostile names stay in the title, subtitle and stdin", async () => {
  const hostile = "x\"; open -a Calculator; $(id) `id` '\n-execute";
  const cases = [
    { where: { place: { kind: "desktop" as const }, session: hostile, project: hostile }, tail: ["-activate", "com.anthropic.claudefordesktop"] },
    { where: { place: { kind: "terminal" as const, tty: "ttys003", bundle: "com.apple.Terminal", app: hostile }, session: hostile }, tail: null },
    { where: { place: { kind: "background" as const, id: "1a2b3c4d" }, session: hostile }, tail: [] },
    { where: { place: { kind: "unknown" as const }, session: hostile }, tail: [] },
  ];
  for (const [index, { where, tail }] of cases.entries()) {
    const { dir, db } = mailbox();
    const tn = fake(dir, "terminal-notifier");
    assert.equal(notifyUndelivered(db, { kind: "approval", messageId: 9, agent: hostile, fromAgent: hostile,
      why: "waiting for your approval in its Claude session", key: `k${index}`, where }, {}, { candidates: [tn] }), true);
    assert.ok(await settled(`${tn}.stdin`));
    // One argument per line in the fake's record; a hostile value contains no raw newline after cleaning.
    const args = readFileSync(`${tn}.args`, "utf8").trimEnd().split("\n");
    assert.deepEqual([args[0], args[2], args[4]], ["-title", "-subtitle", "-group"]);
    const action = args.slice(6);
    if (tail) assert.deepEqual(action, tail);
    else {
      assert.equal(action[0], "-execute");
      assert.equal(action.length, 2);
      assert.ok(action[1].startsWith("/usr/bin/open -b com.apple.Terminal; /usr/bin/osascript "));
    }
    assert.doesNotMatch(action.join("\n"), /Calculator|\$\(id\)|`id`/, "display text never enters the click action");
  }
});

test("the osascript fallback shows the place in its text and has no click action", async () => {
  const { dir, db } = mailbox();
  const osa = fake(dir, "osascript");
  assert.equal(notifyUndelivered(db, { kind: "approval", messageId: 9, agent: "alice", why: "waiting", key: "osa",
    where: { place: { kind: "desktop" }, session: "你好" } }, {}, { candidates: [join(dir, "missing")], osascript: osa }), true);
  assert.ok(await settled(`${osa}.args`));
  const args = readFileSync(`${osa}.args`, "utf8");
  assert.match(args, /#9 · alice · 你好 · Claude desktop app/);
  assert.doesNotMatch(args, /-activate|-execute|com\.anthropic/);
});
