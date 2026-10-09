import type { BridgeMessage } from "./bridge-store.js";

/** A message as returned by a paged read; long bodies may be shortened. */
export interface MessageView extends BridgeMessage {
  bodyTruncated?: true;
  bodyLength?: number;
}

export interface FitOptions {
  /** Total character budget for bodies plus envelopes. */
  maxChars?: number;
  /** Shorten every body to this many characters (preview mode). */
  maxBodyChars?: number;
}

/**
 * Default budget per tool result, in cost units (textCost). Claude Code warns above ~10K tokens and cuts MCP output at
 * 25K tokens by default; 48K units is about 12K tokens in English (≈4 characters per token) and in Chinese
 * (≈1 character per token, counted 4 units each), so it stays inside that in any script (long-messages D151).
 */
export const DEFAULT_PAGE_CHARS = 48_000;
export const MAX_PAGE_CHARS = 400_000;
export const DEFAULT_PAGE_LIMIT = 25;
export const MAX_PAGE_LIMIT = 200;
const ENVELOPE_CHARS = 320;

/** agent-relay long-messages D151: about a token's worth of output per unit; ASCII 1, any other code point 4. */
export function textCost(text: string): number {
  let cost = 0;
  for (const char of text) cost += char.charCodeAt(0) < 0x80 ? 1 : 4;
  return cost;
}

/** The longest prefix of `text` (whole code points) whose cost is at most `budget`. */
export function prefixWithin(text: string, budget: number): string {
  let cost = 0;
  let end = 0;
  for (const char of text) {
    const next = cost + (char.charCodeAt(0) < 0x80 ? 1 : 4);
    if (next > budget) break;
    cost = next;
    end += char.length;
  }
  return text.slice(0, end);
}

function shorten(message: BridgeMessage, budget: number, byCharacters = false): MessageView {
  return {
    ...message,
    body: byCharacters ? Array.from(message.body).slice(0, Math.max(0, budget)).join("")
      : prefixWithin(message.body, Math.max(0, budget)),
    bodyTruncated: true,
    bodyLength: message.body.length,
  };
}

/**
 * Keep messages, in the given order, until the character budget is spent.
 * The first message always returns (shortened if it alone exceeds the budget)
 * so a reader can always make progress.
 */
export function fitMessages(
  messages: BridgeMessage[],
  options: FitOptions = {},
): { messages: MessageView[]; omitted: number } {
  const budget = Math.min(Math.max(options.maxChars ?? DEFAULT_PAGE_CHARS, 1_000), MAX_PAGE_CHARS);
  const views: MessageView[] = [];
  let used = 0;
  for (const message of messages) {
    let view: MessageView =
      options.maxBodyChars !== undefined && message.body.length > options.maxBodyChars
        ? shorten(message, options.maxBodyChars, true)
        : message;
    const size = textCost(view.body) + ENVELOPE_CHARS;
    if (views.length > 0 && used + size > budget) break;
    if (size > budget) view = shorten(message, budget - ENVELOPE_CHARS);
    views.push(view);
    used += Math.min(size, budget);
  }
  return { messages: views, omitted: messages.length - views.length };
}

export function clampLimit(limit: number | undefined, fallback = DEFAULT_PAGE_LIMIT): number {
  return Math.min(Math.max(Math.trunc(limit ?? fallback), 1), MAX_PAGE_LIMIT);
}
