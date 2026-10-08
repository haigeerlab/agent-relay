/** agent-relay legacy-cli-cleanup D95: installing, upgrading, checking and uninstalling belong to the Python runtime. */
export const CLI_COMMANDS = ["retire", "help"] as const;
export type CliCommand = (typeof CLI_COMMANDS)[number];

export interface ParsedCliCommand {
  command: CliCommand;
  keepBacklog: boolean;
  /** Positional argument: the agent for `retire`. */
  target: string | null;
  note: string | null;
}

export function parseCliCommand(args: string[]): ParsedCliCommand {
  const parsed: ParsedCliCommand = { command: "help", keepBacklog: false, target: null, note: null };
  const positionals: string[] = [];
  let help = false;
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--help" || arg === "-h") {
      help = true;
      continue;
    }
    if (arg === "--keep-backlog") {
      parsed.keepBacklog = true;
      continue;
    }
    const [flag, inline] = arg.split(/=(.*)/s, 2);
    if (flag === "--note") {
      const value = inline ?? args[++index];
      if (value === undefined) throw new Error(`${flag} needs a value`);
      parsed.note = value;
      continue;
    }
    if (arg.startsWith("-")) throw new Error(`Unknown option: ${arg}`);
    positionals.push(arg);
  }
  const raw = help ? "help" : positionals[0] ?? "help";
  if (!CLI_COMMANDS.includes(raw as CliCommand)) throw new Error(`Unknown command: ${raw}`);
  parsed.command = raw as CliCommand;
  parsed.target = help ? null : positionals[1] ?? null;
  if (!help && positionals.length > 2) throw new Error(`Unexpected argument: ${positionals[2]}`);
  if (parsed.command === "retire" && !parsed.target) throw new Error("retire needs an agent name");
  return parsed;
}
