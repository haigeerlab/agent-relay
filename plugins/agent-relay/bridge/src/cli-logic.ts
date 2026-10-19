/**
 * agent-relay legacy-cli-cleanup D95: installing, upgrading, checking and uninstalling belong to the Python runtime.
 * script-access D241–D244 adds the script commands: three read-only views, `send` as a script identity, and the
 * user-confirmed registration of a script identity.
 */
export const CLI_COMMANDS = ["retire", "help", "version", "agents", "outbox", "sessions", "send",
  "register-script-identity"] as const;
export type CliCommand = (typeof CLI_COMMANDS)[number];

export interface SendOptions {
  from: string | null;
  to: string | null;
  bodyFile: string | null;
  threadId: string | null;
  idempotencyKey: string | null;
  replyTo: number | null;
  expectsReply: boolean;
  alsoAnswers: number[] | null;
  withdraws: number[] | null;
  wake: boolean;
}

export interface ParsedCliCommand {
  command: CliCommand;
  keepBacklog: boolean;
  /** Positional argument: the agent for `retire`, `outbox` and `register-script-identity`. */
  target: string | null;
  note: string | null;
  confirm: boolean;
  send: SendOptions;
}

const VALUE_FLAGS = new Set(["--note", "--from", "--to", "--body-file", "--thread", "--idempotency-key", "--reply-to",
  "--also-answers", "--withdraws"]);

function idList(flag: string, value: string): number[] {
  const ids = value.split(",").map((part) => part.trim()).filter(Boolean).map(Number);
  if (!ids.length || ids.some((id) => !Number.isInteger(id) || id <= 0)) {
    throw new Error(`${flag} takes message ids separated by commas, for example 12,15`);
  }
  return ids;
}

export function parseCliCommand(args: string[]): ParsedCliCommand {
  const parsed: ParsedCliCommand = {
    command: "help", keepBacklog: false, target: null, note: null, confirm: false,
    send: { from: null, to: null, bodyFile: null, threadId: null, idempotencyKey: null, replyTo: null,
      expectsReply: false, alsoAnswers: null, withdraws: null, wake: true },
  };
  const positionals: string[] = [];
  let help = false;
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--help" || arg === "-h") { help = true; continue; }
    if (arg === "--version") { positionals.unshift("version"); continue; }
    if (arg === "--keep-backlog") { parsed.keepBacklog = true; continue; }
    if (arg === "--confirm") { parsed.confirm = true; continue; }
    if (arg === "--expects-reply") { parsed.send.expectsReply = true; continue; }
    if (arg === "--no-wake") { parsed.send.wake = false; continue; }
    const [flag, inline] = arg.split(/=(.*)/s, 2);
    if (VALUE_FLAGS.has(flag)) {
      const value = inline ?? args[++index];
      if (value === undefined) throw new Error(`${flag} needs a value`);
      if (flag === "--note") parsed.note = value;
      else if (flag === "--from") parsed.send.from = value;
      else if (flag === "--to") parsed.send.to = value;
      else if (flag === "--body-file") parsed.send.bodyFile = value;
      else if (flag === "--thread") parsed.send.threadId = value;
      else if (flag === "--idempotency-key") parsed.send.idempotencyKey = value;
      else if (flag === "--reply-to") parsed.send.replyTo = idList(flag, value)[0];
      else if (flag === "--also-answers") parsed.send.alsoAnswers = idList(flag, value);
      else parsed.send.withdraws = idList(flag, value);
      continue;
    }
    if (arg.startsWith("-")) throw new Error(`Unknown option: ${arg}`);
    positionals.push(arg);
  }
  const raw = help ? "help" : positionals[0] ?? "help";
  if (!CLI_COMMANDS.includes(raw as CliCommand)) throw new Error(`Unknown command: ${raw}`);
  parsed.command = raw as CliCommand;
  parsed.target = help ? null : positionals[1] ?? null;
  if (!help && parsed.command === "send" && positionals.length > 1) {
    // script-access D243: a body on the command line would land in process listings and shell history.
    throw new Error("send reads the body from --body-file or stdin, never from the command line");
  }
  if (!help && positionals.length > 2) throw new Error(`Unexpected argument: ${positionals[2]}`);
  if (parsed.command === "retire" && !parsed.target) throw new Error("retire needs an agent name");
  if (parsed.command === "outbox" && !parsed.target) throw new Error("outbox needs the sender's agent name");
  if (parsed.command === "register-script-identity" && !parsed.target) {
    throw new Error("register-script-identity needs a name");
  }
  if (parsed.command === "send" && (!parsed.send.from || !parsed.send.to)) throw new Error("send needs --from and --to");
  return parsed;
}
