// agent-relay script-inbox-ack D271: bridge_inbox's read, shared by the MCP tool and the runtime CLI's `inbox`.
import type { BridgeStore, InboxOptions } from "./bridge-store.js";
import { deliveryState } from "./delivery.js";
import { continueLines, type ContinueLine, type FitOptions } from "./paging.js";

export interface InboxReadParams extends InboxOptions, FitOptions {
  agent: string;
  messageId?: number;
  bodyOffset?: number;
}

export interface InboxReadOptions {
  /** Whether this read is the identity's own (D99/D100): only then are the read and activity recorded. */
  recorded: boolean;
  /** How a `continue` line tells the reader to fetch the rest of a long body (default: bridge_inbox's wording). */
  continueLine?: ContinueLine;
}

// agent-relay inbox-read-receipt D99, D100: only the identity itself records a read (delivery, wake) or activity;
// anyone may still list. The result says which, so a bystander knows it changed nothing.
export function readReceipt(agent: string, recorded: boolean) {
  return recorded
    ? { readRecorded: true }
    : {
        readRecorded: false,
        readNote: `This read was not recorded: ${JSON.stringify(agent)} is not an identity of this session, so its messages ` +
          "stay unread for delivery and its recipient will still be pinged. If " + JSON.stringify(agent) + " is this " +
          "session's own name (for example after the bridge restarted), call bridge_register with it from this session again.",
      };
}

export function readInbox(store: BridgeStore, params: InboxReadParams, options: InboxReadOptions): Record<string, unknown> {
  const { agent, messageId, bodyOffset, maxChars } = params;
  const { recorded } = options;
  // agent-relay mailbox-polish D154: a view shows the delivery state after the read this call recorded.
  const afterRead = <T extends { id: number; deliveryState: unknown }>(view: T): T =>
    ({ ...view, deliveryState: deliveryState(store.database, view.id) });
  // agent-relay long-messages D152: one message, one part of its body.
  if (messageId !== undefined) {
    const message = store.messagePart(agent, messageId, { bodyOffset, maxChars });
    if (!message) {
      // agent-relay read-own-sent D213: say why, as a fact, and whom to ask; never point at another inbox.
      const parties = store.messageParties(messageId);
      if (!parties) throw new Error(`There is no message #${messageId}.`);
      throw new Error(`Message #${messageId} was not sent to ${JSON.stringify(agent)} and not sent by it; by id an ` +
        `agent reads only messages it received or sent. For the text, ask its sender ${JSON.stringify(parties.from)} ` +
        `or its recipient ${JSON.stringify(parties.to)}.`);
    }
    // presence-polish D177: an offset past the end is a mistake to report, not an empty part.
    const length = message.bodyLength ?? message.body.length;
    if (bodyOffset !== undefined && bodyOffset > length) {
      throw new Error(`bodyOffset ${bodyOffset} is past the end of message #${messageId} (${length} characters).`);
    }
    // read-own-sent D212: reading back a sent message records nothing, for the sender or its recipient.
    if (recorded && message.direction === "received") {
      store.wakes.recordRead(agent, [message.id]);
      store.touch(agent);
    }
    const receipt = message.direction === "sent"
      ? { readRecorded: false, readNote: `Message #${message.id} was sent by ${JSON.stringify(agent)}; reading it back ` +
          "records nothing for it or its recipient." }
      : readReceipt(agent, recorded);
    return { agent, message: afterRead(message), ...receipt };
  }
  const { includeAcknowledged, fromAgent, threadId, afterId, includeExpired, limit, maxBodyChars } = params;
  const page = store.inboxPage(agent, { includeAcknowledged, fromAgent, threadId, afterId, includeExpired, limit, maxChars, maxBodyChars });
  if (recorded) {
    store.wakes.recordRead(agent, page.messages.map((message) => message.id));
    store.touch(agent);
  }
  const more = continueLines(page.messages, agent, options.continueLine);
  return { agent, ...page, messages: page.messages.map(afterRead), ...(more.length ? { continue: more } : {}),
    ...readReceipt(agent, recorded) };
}
