// agent-relay idempotency (D33, D34): one retry key means one message.

/** The fields that make up a message's content for a retry; delivery options (wake, timeout) are not content. */
export interface MessageContent {
  toAgent: string;
  body: string;
  threadId: string | null;
  replyTo: number | null;
}

export class IdempotencyConflictError extends Error {}

/** A reply that names no stored message, or a thread other than its original's (D36). */
export class ReplyLinkError extends Error {}

/**
 * agent-relay identity-check (assumption 5): only a message's recipient may reply to it; a broadcast takes replies
 * from anyone but its sender; the bridge's automated notices take none.
 */
export function assertMayReply(originalId: number, originalFrom: string, originalTo: string, sender: string): void {
  if (originalFrom === "bridge") {
    throw new ReplyLinkError(`Message #${originalId} is an automated notice from "bridge"; do not reply to it.`);
  }
  if (originalTo === "*") {
    if (sender === originalFrom) {
      throw new ReplyLinkError(`"${sender}" cannot reply to its own broadcast #${originalId}; send a new message instead.`);
    }
    return;
  }
  if (sender !== originalTo) {
    throw new ReplyLinkError(
      `Only "${originalTo}", the recipient of message #${originalId}, may reply to it; "${sender}" may send a new ` +
        "message on the same thread instead.",
    );
  }
}

/** The thread a reply goes on: the original's, which an explicit threadId must match (D36). */
export function replyThread(originalId: number, originalThread: string | null, requested: string | null | undefined): string | null {
  if (requested == null || requested === originalThread) return originalThread;
  const where = originalThread === null ? "has no thread" : `is on thread "${originalThread}"`;
  throw new ReplyLinkError(
    `Message #${originalId} ${where}, so its reply must be on the same thread, not "${requested}". ` +
      "Omit threadId to use the original's thread.",
  );
}

/** Names of the content fields in which a retry differs from the stored message. */
export function contentDifferences(stored: MessageContent, retry: MessageContent): string[] {
  return (["toAgent", "body", "threadId", "replyTo"] as const).filter((field) => stored[field] !== retry[field]);
}

/**
 * The refusal for a reused key with different content. The sender may be a delegated session retrying a result, so
 * the text says the earlier message is already stored and that nothing needs to be re-sent.
 */
export function conflictError(key: string, sender: string, storedId: number, deliveryState: string | null,
  fields: string[]): IdempotencyConflictError {
  const state = deliveryState ?? "broadcast";
  return new IdempotencyConflictError(
    `Idempotency key "${key}" was already used by "${sender}" for message #${storedId} (deliveryState: ${state}), ` +
      `which is already stored and in delivery, so no resend is needed. This send differs in ${fields.join(", ")}, ` +
      "so nothing new was stored. To send a different message, use a new idempotency key.",
  );
}

/** The warning on a send that returned an already stored message. */
export function duplicateWarning(id: number): string {
  return `Message already stored as message #${id}; not sent again.`;
}
