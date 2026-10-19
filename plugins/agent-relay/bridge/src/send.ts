// agent-relay script-access D243: one bridge_send, shared by the MCP tool and the runtime CLI's `send`.
import type { AgentHost, BridgeStore } from "./bridge-store.js";
import { checkRecipient } from "./addressing.js";
import { pendingWarning } from "./delivery.js";
import { duplicateWarning } from "./idempotency.js";
import { NOTIFIED_TEXT, notifyUndelivered } from "./notify.js";
import type { Presence } from "./presence.js";
import { codexOwner } from "./presence.js";
import { CODEX_ASK } from "./views.js";

export interface SendRequest {
  from: string;
  to: string;
  body: string;
  threadId?: string;
  idempotencyKey?: string;
  replyTo?: number;
  expectsReply?: boolean;
  alsoAnswers?: number[];
  withdraws?: number[];
  wake?: boolean;
  allowUnregistered?: boolean;
  expiresInSeconds?: number;
}

export interface SendContext {
  dbPath: string;
  presenceOf: (host: AgentHost) => Promise<Presence>;
  /** Dispatch due pings once (the bridge's WakeDispatcher.flush). */
  flush: () => Promise<void>;
}

/** Store the message, add bridge_send's warnings, dispatch once, and return bridge_send's result object. */
export async function sendMessage(store: BridgeStore, request: SendRequest, context: SendContext) {
  const { from, to, body, threadId, idempotencyKey, replyTo, expectsReply, alsoAnswers, withdraws, wake,
    allowUnregistered, expiresInSeconds } = request;
  const check = await checkRecipient(store, to, { allowUnregistered, presenceOf: context.presenceOf });
  if (!check.ok) throw new Error(check.error);
  const warnings = [...check.warnings];
  const { message, duplicate, closed, skipped } = store.deliver({
    wake,
    fromAgent: from,
    toAgent: to,
    body,
    threadId: threadId ?? null,
    idempotencyKey: idempotencyKey ?? null,
    replyTo: replyTo ?? null,
    expectsReply: expectsReply === true,
    alsoAnswers,
    withdraws,
    expiresInSeconds,
  });
  store.touch(from);
  if (duplicate) warnings.push(duplicateWarning(message.id));
  if (to !== "*") {
    const capWarning = pendingWarning(store.database, to);
    if (capWarning) warnings.push(capWarning);
    // agent-relay codex-gated-wake D67: a recorded Codex recipient with no wake binding would never hear of it.
    const recipient = store.getAgent(to);
    // notice-location D188: "Codex app" (and a click) only when the app itself says it holds that thread.
    if (!duplicate && wake !== false && recipient?.host?.app === "codex" && !store.wakes.target(to)
        && notifyUndelivered(context.dbPath, { messageId: message.id, fromAgent: from, agent: to,
          why: "its Codex session has no wake binding; the message waits", body,
          where: { place: { kind: (await codexOwner(recipient.host.sessionId, undefined, CODEX_ASK)) === true ? "codex-app" : "codex" } } })) {
      warnings.push(`${JSON.stringify(to)} is a Codex session without a wake binding. ${NOTIFIED_TEXT}`);
    }
    // agent-relay acceptance-030-gaps D72: with no binding and no recorded host nobody can be woken or notified.
    if (!duplicate && wake !== false && recipient && !recipient.host && !store.wakes.target(to)) {
      warnings.push(`${JSON.stringify(to)} has no wake binding and no known host; ` +
        "it sees this message only when it reads its inbox.");
    }
  }
  await context.flush();
  // agent-relay long-messages D150: the sender never gets its own body back, only its length.
  const { body: _sentBody, ...stored } = message;
  return {
    ...stored,
    bodyLength: message.body.length,
    wake: store.wakes.forMessage(message.id),
    ...(duplicate ? { duplicate } : {}),
    // agent-relay request-closing D222: what this send closed, so a session can tell an old bridge that dropped it.
    // Revision D238: what it skipped because it was already closed; nothing to redo for those.
    ...(alsoAnswers !== undefined || withdraws !== undefined ? { closed, skipped } : {}),
    ...(warnings.length ? { warnings } : {}),
  };
}
