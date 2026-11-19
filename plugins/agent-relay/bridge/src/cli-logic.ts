/**
 * agent-relay legacy-cli-cleanup D95: installing, upgrading, checking and uninstalling belong to the Python runtime.
 * script-access D241–D244 adds the script commands: three read-only views, `send` as a script identity, and the
 * user-confirmed registration of a script identity. script-inbox-ack D271, D272 adds `inbox` and `ack`, which act only
 * as a script identity.
 */
export const CLI_COMMANDS = ["retire", "help", "version", "agents", "outbox", "sessions", "send",
  "register-script-identity", "inbox", "ack"] as const;
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

/** bridge_inbox's fields; null (false) when not given. */
export interface InboxCliOptions {
  fromAgent: string | null;
  threadId: string | null;
  afterId: number | null;
  includeAcknowledged: boolean;
  includeExpired: boolean;
  limit: number | null;
  maxChars: number | null;
  maxBodyChars: number | null;
  messageId: number | null;
  bodyOffset: number | null;
}

export interface ParsedCliCommand {
  command: CliCommand;
  keepBacklog: boolean;
  /** Positional argument: the agent for `retire`, `outbox`, `register-script-identity`, `inbox` and `ack`. */
  target: string | null;
  note: string | null;
  confirm: boolean;
  send: SendOptions;
  inbox: InboxCliOptions;
  /** `ack --ids`: the message ids to acknowledge. */
  ackIds: number[] | null;
}

const VALUE_FLAGS = new Set(["--note", "--from", "--to", "--body-file", "--thread", "--idempotency-key", "--reply-to",
  "--also-answers", "--withdraws", "--ids", "--from-agent", "--after-id", "--limit", "--max-chars", "--max-body-chars",
  "--message-id", "--body-offset"]);

/** script-inbox-ack D271: bridge_inbox's ranges, so the CLI refuses what the MCP schema refuses. */
const RANGES: Record<string, [number, number?]> = {
  "--after-id": [0], "--limit": [1, 200], "--max-chars": [1000, 400000], "--max-body-chars": [0, 400000],
  "--message-id": [1], "--body-offset": [0],
};

function wholeNumber(flag: string, value: string): number {
  const [min, max] = RANGES[flag];
  const number = /^\d+$/.test(value.trim()) ? Number(value) : NaN;
  if (!Number.isSafeInteger(number) || number < min || (max !== undefined && number > max)) {
    throw new Error(`${flag} takes a whole number from ${min}${max === undefined ? "" : ` to ${max}`}`);
  }
  return number;
}

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
    inbox: { fromAgent: null, threadId: null, afterId: null, includeAcknowledged: false, includeExpired: false,
      limit: null, maxChars: null, maxBodyChars: null, messageId: null, bodyOffset: null },
    ackIds: null,
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
    if (arg === "--include-acknowledged") { parsed.inbox.includeAcknowledged = true; continue; }
    if (arg === "--include-expired") { parsed.inbox.includeExpired = true; continue; }
    const [flag, inline] = arg.split(/=(.*)/s, 2);
    if (VALUE_FLAGS.has(flag)) {
      const value = inline ?? args[++index];
      if (value === undefined) throw new Error(`${flag} needs a value`);
      if (flag === "--note") parsed.note = value;
      else if (flag === "--from") parsed.send.from = value;
      else if (flag === "--to") parsed.send.to = value;
      else if (flag === "--body-file") parsed.send.bodyFile = value;
      else if (flag === "--thread") { parsed.send.threadId = value; parsed.inbox.threadId = value; }
      else if (flag === "--from-agent") parsed.inbox.fromAgent = value;
      else if (flag === "--ids") parsed.ackIds = idList(flag, value);
      else if (flag in RANGES) {
        const key = ({ "--after-id": "afterId", "--limit": "limit", "--max-chars": "maxChars",
          "--max-body-chars": "maxBodyChars", "--message-id": "messageId", "--body-offset": "bodyOffset" } as const)[
          flag as "--after-id" | "--limit" | "--max-chars" | "--max-body-chars" | "--message-id" | "--body-offset"];
        parsed.inbox[key] = wholeNumber(flag, value);
      }
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
  if (!help && (parsed.command === "inbox" || parsed.command === "ack")) {
    if (!parsed.target) throw new Error(`${parsed.command} needs the script identity's name`);
    if (parsed.send.from !== null) {
      throw new Error(parsed.command === "inbox" ? "--from is for send; inbox filters senders with --from-agent"
        : "--from is for send; ack names the script identity as its argument");
    }
  }
  if (!help && parsed.command === "inbox" && parsed.inbox.bodyOffset !== null && parsed.inbox.messageId === null) {
    throw new Error("--body-offset needs --message-id");
  }
  if (!help && parsed.command === "ack" && !parsed.ackIds) throw new Error("ack needs --ids, for example --ids 12,15");
  return parsed;
}
