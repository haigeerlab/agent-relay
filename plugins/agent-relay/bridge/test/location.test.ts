// agent-relay notice-location D188: where a session is, what the notice says about it, and what a click may run.
import assert from "node:assert/strict";
import test from "node:test";

import { CLAUDE_DESKTOP, CODEX_APP, ITERM, TERMINAL, clickArgs, locate, outermostApp, placeCategory, placeLabel,
  validBundle, validTty } from "../src/location.js";

const cli = { entrypoint: "cli", kind: "interactive", sessionId: "1a2b3c4d-0817-479d-886e-772bafbbee6f" };

test("a session is placed from its registry entry, its tty and the app that owns its terminal", () => {
  assert.deepEqual(locate({ ...cli, entrypoint: "claude-desktop" }, null, null), { kind: "desktop" });
  assert.deepEqual(locate(cli, "ttys003", { bundle: TERMINAL, name: "Terminal" }),
    { kind: "terminal", tty: "ttys003", bundle: TERMINAL, app: "Terminal" });
  assert.deepEqual(locate(cli, "ttys003", null), { kind: "terminal", tty: "ttys003", bundle: null, app: null },
    "tmux, screen or ssh: no app in the parent chain");
  assert.deepEqual(locate({ ...cli, kind: "background" }, null, null), { kind: "background", id: "1a2b3c4d" });
  assert.deepEqual(locate(cli, null, null), { kind: "unknown" });
  assert.deepEqual(locate(cli, "ttys1; rm -rf ~", null), { kind: "unknown" }, "a tty that fails its format is not a place");
  assert.deepEqual(locate({ ...cli, kind: "background", sessionId: "$(id)-x" }, null, null), { kind: "unknown" });
  assert.deepEqual(locate({ sessionId: cli.sessionId }, "ttys003", null), { kind: "unknown" }, "no entrypoint: not guessed");
});

test("formats are strict: tty, bundle id, and the outermost .app of a nested path", () => {
  assert.equal(validTty("ttys000"), "ttys000");
  for (const bad of ["??", "", "ttys", "ttys0\n1", "/dev/ttys000", "ttys000 x", "console"]) assert.equal(validTty(bad), null, bad);
  assert.equal(validBundle("dev.warp.Warp-Stable"), "dev.warp.Warp-Stable");
  for (const bad of ["", "a b", "x;y", "$(id)", "a'b", "a".repeat(129), "com.x\n", "-help", ".x", "-activate"]) {
    assert.equal(validBundle(bad), null, bad); // never an option-looking value for -activate (review of #84)
  }
  assert.equal(outermostApp("/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper.app/Contents/MacOS/Code Helper"),
    "/Applications/Visual Studio Code.app");
  assert.equal(outermostApp("/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal"),
    "/System/Applications/Utilities/Terminal.app");
  assert.equal(outermostApp("/opt/homebrew/bin/tmux"), null);
  assert.equal(outermostApp("relative/X.app/Contents/MacOS/x"), null);
});

test("the label names the place; the category hides the tty and the attach id", () => {
  assert.equal(placeLabel({ kind: "desktop" }), "Claude desktop app");
  assert.equal(placeLabel({ kind: "terminal", tty: "ttys003", bundle: TERMINAL, app: "Terminal" }), "Terminal ttys003");
  assert.equal(placeLabel({ kind: "terminal", tty: "ttys003", bundle: null, app: null }), "terminal ttys003");
  assert.equal(placeLabel({ kind: "background", id: "1a2b3c4d" }), "background session · claude attach 1a2b3c4d");
  assert.equal(placeLabel({ kind: "codex-app" }), "Codex app");
  assert.equal(placeLabel({ kind: "codex" }), "Codex");
  assert.equal(placeLabel({ kind: "unknown" }), "");
  assert.equal(placeCategory({ kind: "terminal", tty: "ttys003", bundle: TERMINAL, app: "Terminal" }), "terminal");
  assert.equal(placeCategory({ kind: "background", id: "1a2b3c4d" }), "background session");
});

test("a click activates an app, or runs one fixed command that carries only a bundle id and a tty", () => {
  assert.deepEqual(clickArgs({ kind: "desktop" }), ["-activate", CLAUDE_DESKTOP]);
  assert.deepEqual(clickArgs({ kind: "codex-app" }), ["-activate", CODEX_APP]);
  assert.deepEqual(clickArgs({ kind: "terminal", tty: "ttys003", bundle: "dev.warp.Warp-Stable", app: "Warp" }),
    ["-activate", "dev.warp.Warp-Stable"]);
  for (const place of [{ kind: "codex" }, { kind: "unknown" }, { kind: "background", id: "1a2b3c4d" },
    { kind: "terminal", tty: "ttys003", bundle: null, app: null }] as const) assert.deepEqual(clickArgs(place), []);

  for (const [bundle, application] of [[TERMINAL, "Terminal"], [ITERM, "iTerm2"]] as const) {
    const [flag, command, ...rest] = clickArgs({ kind: "terminal", tty: "ttys003", bundle, app: "whatever \"name\" $(id)" });
    assert.equal(flag, "-execute");
    assert.deepEqual(rest, []);
    assert.ok(command.startsWith(`/usr/bin/open -b ${bundle}; /usr/bin/osascript -e '`), command);
    assert.match(command, new RegExp(`tell application "${application}"`));
    assert.match(command, /"\/dev\/ttys003"/);
    assert.doesNotMatch(command, /whatever|\$\(id\)/, "the app's display name never enters the command");
    // Program paths: exactly these two, nothing else that looks like a path except the tty device.
    assert.deepEqual([...new Set(command.match(/\/[A-Za-z0-9_./-]+/g))].sort(), ["/dev/ttys003", "/usr/bin/open", "/usr/bin/osascript"]);
    assert.equal((command.match(/'/g) ?? []).length % 2, 0, "balanced single quotes");
  }
  // A place built by hand with a hostile tty or bundle gets no action at all.
  assert.deepEqual(clickArgs({ kind: "terminal", tty: "ttys1'; open /", bundle: TERMINAL, app: null }), []);
  assert.deepEqual(clickArgs({ kind: "terminal", tty: "ttys003", bundle: "x; rm", app: null }), []);
});
