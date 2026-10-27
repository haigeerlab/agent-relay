import type { BridgeStore } from "./bridge-store.js";
import { CLAUDE_EXPIRED_RECEIPT } from "./claude-wake.js";
import { acceptedUnreadText } from "./notify.js";
import { type AcceptedUnread, CLAUDE_HOLD_GRACE_MS, type WakeJob } from "./wake-queue.js";

export { CLAUDE_HOLD_GRACE_MS };

/**
 * Reserved sender for automated notices: delivery failures, retirements and
 * Codex run results. It never registers, and its own messages never trigger
 * further notices, so notices cannot loop.
 */
export const BRIDGE_AGENT = "bridge";

/** At most one delivery-failure notice per sender/recipient pair per window. */
const NOTICE_WINDOW_MS = 30 * 60_000;

/**
 * agent-relay delivery-robustness D260 (revises the D215 text): Claude's receipt names no cause. Every hold seen so far
 * was a session that had just started; Bypass permissions is the case that lasts.
 */
export const CLAUDE_HOLD_EXPLANATION =
  "Claude Code held this message by permission-mode parity. Usually the recipient session has just started: Claude " +
  "releases the message within seconds and it is then delivered. A hold that lasts may mean the session runs in Bypass " +
  "permissions while the sender states no permission mode (Claude Code's crossSessionInbound setting); the desktop app " +
  "shows no approval prompt for that, so the message expires unread. The user can switch that session out of Bypass " +
  "permissions, approve held messages in a terminal session, or deliberately set \"crossSessionInbound\": \"accept\" in " +
  "~/.claude/settings.json. The bridge never changes that setting. Do not resend while the message is held.";

/** agent-relay expiry-notice-reason D215: a Claude ping that expired because its session was not running. */
export const CLAUDE_OFFLINE_EXPLANATION =
  "The recipient's Claude session was not running for the whole one-hour retry window (the Claude app may stop idle " +
  "sessions). The message stays in its inbox and is delivered once that session is opened: ask the user to open it.";

/**
 * agent-relay expiry-notice-reason D215: only Claude's own word makes a hold: the ping is `held`, or Claude's receipt
 * said it expired the message. Bridge-written details (an offline expiry, a re-armed ping) never count, whatever words
 * they contain. Takes a wake job's fields or a `health()` row.
 */
export function isClaudeHold(ping: { app: string; state: string; detail: string }): boolean {
  return ping.app === "claude" && (ping.state === "held" || (ping.state === "refused" && ping.detail === CLAUDE_EXPIRED_RECEIPT));
}

/** A Claude ping that expired while its session was not running (D215). */
export function isClaudeOfflineExpiry(ping: { app: string; state: string; pendingReason?: string | null }): boolean {
  return ping.app === "claude" && ping.state === "expired" && (ping.pendingReason ?? "offline") === "offline";
}

export function explainFailure(job: WakeJob): string {
  if (isClaudeHold({ app: job.target.app, state: job.state, detail: job.detail })) return CLAUDE_HOLD_EXPLANATION;
  if (job.state === "expired") {
    if (isClaudeOfflineExpiry({ app: job.target.app, state: job.state, pendingReason: job.pendingReason })) {
      return CLAUDE_OFFLINE_EXPLANATION;
    }
    return job.pendingReason === "busy"
      ? "The recipient stayed busy for the whole 24-hour retry window."
      : "The recipient's app session was unreachable for the whole one-hour retry window.";
  }
  return `The recipient app reported: ${job.detail}`;
}

/**
 * accepted-unread-notice D230: tell the sender, once per message, that its accepted Codex message has not been read.
 * The idempotency key keeps it to one message across bridges; the same rules as delivery failures decide who is told.
 */
export function noticeAcceptedUnread(store: BridgeStore, entry: AcceptedUnread): void {
  const sender = entry.fromAgent;
  if (!sender || sender === BRIDGE_AGENT || sender === entry.agent) return;
  const agent = store.getAgent(sender);
  if (!agent || agent.retiredAt) return;
  store.send({
    fromAgent: BRIDGE_AGENT,
    toAgent: sender,
    threadId: entry.threadId,
    body: [
      `Delivery in doubt: your message #${entry.messageId} to ${JSON.stringify(entry.agent)} was accepted but has not been read.`,
      acceptedUnreadText(entry.agent, entry.messageId, sender, entry.acceptedAt),
      "The user was told on this Mac (desktop notifications allowing). bridge_outbox shows wake.doubt until it is read.",
      "This is an automated bridge notice. Do not reply to it.",
    ].join("\n\n"),
    idempotencyKey: `accepted-unread:${entry.messageId}`,
  });
}

export function deliveryFailureNotice(job: WakeJob): string {
  const target = `${JSON.stringify(job.agent)}${job.threadId ? ` (thread ${JSON.stringify(job.threadId)})` : ""}`;
  // agent-relay delivery-state-machine (D27): the message itself expired, so unlike a lapsed ping it is no
  // longer waiting in the inbox and will never be acted on.
  if (job.deliveryState === "expired") {
    return [
      `Delivery problem: your message #${job.messageId} to ${target} expired before it was delivered: its queue timeout passed while it was still waiting.`,
      `It will not be delivered, pinged or shown in ${JSON.stringify(job.agent)}'s inbox. If the work is still wanted, send it again as a new message, or give it to another agent.`,
      "This is an automated bridge notice. Do not reply to it.",
    ].join("\n\n");
  }
  const outcome =
    job.state === "held"
      ? job.target.app === "codex"
        ? "was held before it reached Codex"
        : `has been held by the recipient's Claude session for more than ${CLAUDE_HOLD_GRACE_MS / 1000} seconds`
      : `ended "${job.state}"`;
  return [
    `Delivery problem: your message #${job.messageId} to ${target} was saved, but its background ping ${outcome}.`,
    `Why: ${explainFailure(job)}`,
    `The message is still unread in ${JSON.stringify(job.agent)}'s inbox. Options: send the work to another agent, ask the user to open that conversation, or check bridge_outbox for everything still unhandled.`,
    "This is an automated bridge notice. Do not reply to it.",
  ].join("\n\n");
}

/**
 * Tell senders when a background ping fails, so work does not silently stall.
 * Each failed ping is claimed atomically, so several bridge processes can run
 * this concurrently. Returns how many failures were processed.
 */
export function sweepDeliveryFailures(store: BridgeStore, now = Date.now(), max = 20): number {
  let processed = 0;
  for (; processed < max; processed += 1) {
    const job = store.wakes.claimFailure(now);
    if (!job) break;
    const sender = job.fromAgent;
    if (!sender || sender === BRIDGE_AGENT || sender === job.agent) continue;
    const agent = store.getAgent(sender);
    if (!agent || agent.retiredAt) continue;
    store.send({
      fromAgent: BRIDGE_AGENT,
      toAgent: sender,
      threadId: job.threadId ?? null,
      body: deliveryFailureNotice(job),
      idempotencyKey: `delivery:${sender}->${job.agent}:${Math.floor(now / NOTICE_WINDOW_MS)}`,
    });
  }
  return processed;
}
