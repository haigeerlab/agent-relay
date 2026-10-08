#!/usr/bin/env node

import { BridgeStore } from "./bridge-store.js";
import { parseCliCommand, type ParsedCliCommand } from "./cli-logic.js";
import { retireAgent } from "./lifecycle.js";
import { defaultDbPath } from "./paths.js";
import { VERSION } from "./version.js";

// agent-relay legacy-cli-cleanup D95: only `retire` (run by native_collaboration_retire.py) and `help` remain; the
// Python runtime installs, upgrades, checks and uninstalls.
const USAGE = `Usage:
  agent-relay-bridge <command> [options]

Commands:
  retire <agent> [--note TEXT] [--keep-backlog]
                                  Retire a finished agent and close its unhandled messages
  help                            Show this help

Install, upgrade, check and uninstall with agent-relay's native_collaboration_runtime.py.
`;

function retire(parsed: ParsedCliCommand): number {
  const store = new BridgeStore(defaultDbPath());
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
  process.exitCode = parsed.command === "retire" ? retire(parsed) : help();
}

main();
