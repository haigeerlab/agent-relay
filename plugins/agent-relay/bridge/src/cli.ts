#!/usr/bin/env node

import { readFileSync } from "node:fs";

import { readBodyFile } from "./body-file.js";
import { BridgeStore } from "./bridge-store.js";
import { claudeSessions } from "./claude-wake.js";
import { parseCliCommand, type ParsedCliCommand } from "./cli-logic.js";
import { retireAgent } from "./lifecycle.js";
import { sendMessage } from "./send.js";
import { VERSION } from "./version.js";
import { agentsView, hostPresence, outboxView, sessionsView } from "./views.js";
import { WakeDispatcher } from "./wake-dispatcher.js";

// agent-relay legacy-cli-cleanup D95: only `retire` (run by native_collaboration_retire.py) and `help` remain; the
// Python runtime installs, upgrades, checks and uninstalls.
const USAGE = `Usage:
  agent-relay-bridge <command> [options]

Commands:
  retire <agent> [--note TEXT] [--keep-backlog]
                                  Retire a finished agent and close its unhandled messages
                                  (needs BRIDGE_DB_PATH; run by native_collaboration_retire.py)
  agents                          Print bridge_agents' result (read-only)
  outbox <agent>                  Print bridge_outbox's result for <agent> (read-only)
  sessions                        Print bridge_sessions' result (read-only)
  send --from <script identity> --to <agent> [--body-file PATH]
       [--expects-reply] [--reply-to ID] [--thread ID] [--also-answers IDS] [--withdraws IDS]
       [--idempotency-key KEY] [--no-wake]
                                  Send as a script identity; the body comes from --body-file or stdin
  register-script-identity <name> [--confirm]
                                  Record <name> as a script identity (only with --confirm)
  help                            Show this help
  --version                       Print the version

Script commands read BRIDGE_DB_PATH; run them through ~/.agent-relay/bin/agent-relay.

Install, upgrade, check and uninstall with agent-relay's native_collaboration_runtime.py.
`;

// agent-relay retire-cli-guard D111: retire opens only the mailbox it is given, never the upstream default database.
const NO_MAILBOX = "retire needs BRIDGE_DB_PATH (the agent-relay mailbox); retire an identity with "
  + "native_collaboration_retire.py --name <agent> --confirm-retire";

function retire(parsed: ParsedCliCommand): number {
  const dbPath = process.env.BRIDGE_DB_PATH?.trim();
  if (!dbPath) {
    console.error(NO_MAILBOX);
    return 2;
  }
  const store = new BridgeStore(dbPath);
  try {
    const result = retireAgent(store, parsed.target as string, {
      by: "operator",
      note: parsed.note ?? undefined,
      closeBacklog: !parsed.keepBacklog,
    });
    console.log(`✓ Retired ${result.agent.name}${result.unbound ? " and removed its ping binding" : ""}`);
    console.log(`  Closed ${result.closed} unhandled message(s)${result.notified.length ? `; notified ${result.notified.join(", ")}` : ""}`);
    return 0;
  } catch (error) {
    console.error(`✗ ${error instanceof Error ? error.message : String(error)}`);
    return 1;
  } finally {
    store.close();
  }
}

// agent-relay script-access D242: a script gets one sentence on stderr and a non-zero exit, never a stack.
function fail(error: unknown, code = 1): number {
  console.error((error instanceof Error ? error.message : String(error)).split("\n")[0]);
  return code;
}

function mailboxPath(): string | null {
  const dbPath = process.env.BRIDGE_DB_PATH?.trim();
  return dbPath ? dbPath : null;
}

const NO_SCRIPT_MAILBOX = "BRIDGE_DB_PATH is not set; run script commands through ~/.agent-relay/bin/agent-relay.";

async function read(parsed: ParsedCliCommand): Promise<number> {
  const dbPath = mailboxPath();
  if (!dbPath) return fail(NO_SCRIPT_MAILBOX, 2);
  let store: BridgeStore;
  try {
    store = new BridgeStore(dbPath, { readOnly: true });
  } catch (error) {
    return fail(error);
  }
  try {
    let result: unknown;
    if (parsed.command === "agents") result = await agentsView(store, {});
    else if (parsed.command === "outbox") result = await outboxView(store, { agent: parsed.target as string });
    else {
      const scripts = store.agents().filter((agent) => agent.host?.app === "script" && !agent.retiredAt);
      result = sessionsView(await claudeSessions(), {
        mailboxPath: dbPath, thisSession: null, codexSessionId: null, channelMode: "off",
        whoami: { host: null, sessionName: null, project: null,
          identities: scripts.map((agent) => ({ name: agent.name, provenHere: true, recordedHost: agent.host, wake: null })),
          note: "A script is not a session; it sends only as a script identity." },
      });
    }
    process.stdout.write(JSON.stringify(result) + "\n");
    return 0;
  } catch (error) {
    return fail(error);
  } finally {
    store.close();
  }
}

function registerScript(parsed: ParsedCliCommand): number {
  const dbPath = mailboxPath();
  if (!dbPath) return fail(NO_SCRIPT_MAILBOX, 2);
  const name = parsed.target as string;
  if (!parsed.confirm) {
    console.log(`Would record "${name}" as a script identity: only agent-relay send acts as it, no session can, and it ` +
      "is never woken. Run again with --confirm once the user agrees.");
    return 0;
  }
  let store: BridgeStore;
  try {
    store = new BridgeStore(dbPath);
  } catch (error) {
    return fail(error);
  }
  try {
    const agent = store.registerScriptIdentity(name);
    process.stdout.write(JSON.stringify({ registered: agent.name, host: agent.host }) + "\n");
    return 0;
  } catch (error) {
    return fail(error);
  } finally {
    store.close();
  }
}

/** A Claude receipt that arrives after the adapter's first wait is still recorded before the CLI exits. */
async function settle(store: BridgeStore, messageId: number, limitMs = 5000): Promise<void> {
  const deadline = Date.now() + limitMs;
  while (Date.now() < deadline) {
    const wake = store.wakes.forMessage(messageId);
    if (!wake || !/awaiting Claude receipt/.test(wake.detail ?? "")) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
}

async function send(parsed: ParsedCliCommand): Promise<number> {
  const dbPath = mailboxPath();
  if (!dbPath) return fail(NO_SCRIPT_MAILBOX, 2);
  const options = parsed.send;
  let body: string;
  try {
    if (options.bodyFile) body = readBodyFile(options.bodyFile);
    else if (process.stdin.isTTY) throw new Error("send reads the body from --body-file or stdin; stdin is a terminal");
    else body = readFileSync(0, "utf8");
    if (!body) throw new Error("The body is empty.");
  } catch (error) {
    return fail(error, 2);
  }
  let store: BridgeStore;
  try {
    store = new BridgeStore(dbPath);
  } catch (error) {
    return fail(error);
  }
  const dispatcher = new WakeDispatcher(store);
  try {
    // agent-relay script-access D244: the CLI acts only as a script identity.
    const sender = store.getAgent(options.from as string);
    if (!sender || sender.host?.app !== "script" || sender.retiredAt) {
      throw new Error(`"${options.from}" is not a script identity; register one with register-script-identity <name> --confirm.`);
    }
    const result = await sendMessage(store, {
      from: options.from as string, to: options.to as string, body,
      threadId: options.threadId ?? undefined, idempotencyKey: options.idempotencyKey ?? undefined,
      replyTo: options.replyTo ?? undefined, expectsReply: options.expectsReply,
      alsoAnswers: options.alsoAnswers ?? undefined, withdraws: options.withdraws ?? undefined, wake: options.wake,
    }, { dbPath, presenceOf: hostPresence, flush: () => dispatcher.flush() });
    await settle(store, result.id);
    process.stdout.write(JSON.stringify({ ...result, wake: store.wakes.forMessage(result.id) }) + "\n");
    return 0;
  } catch (error) {
    return fail(error);
  } finally {
    await dispatcher.close();
    store.close();
  }
}

function help(): number {
  console.log(`agent-relay-bridge ${VERSION}\n\n${USAGE}`);
  return 0;
}

function main(): void {
  let parsed: ParsedCliCommand;
  try {
    parsed = parseCliCommand(process.argv.slice(2));
  } catch (error) {
    console.error(`${error instanceof Error ? error.message : String(error)}\n\n${USAGE}`);
    process.exitCode = 2;
    return;
  }
  switch (parsed.command) {
    case "retire": process.exitCode = retire(parsed); return;
    case "version": console.log(VERSION); process.exitCode = 0; return;
    case "agents": case "outbox": case "sessions": void read(parsed).then((code) => { process.exitCode = code; }); return;
    case "send": void send(parsed).then((code) => { process.exitCode = code; }); return;
    case "register-script-identity": process.exitCode = registerScript(parsed); return;
    default: process.exitCode = help();
  }
}

main();
