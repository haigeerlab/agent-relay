// agent-relay idempotency (D33, D34): one retry key means one message.

/** The fields that make up a message's content for a retry; delivery options (wake, timeout) are not content. */
export interface MessageContent {
  toAgent: string;
  body: string;
  threadId: string | null;
}

export class IdempotencyConflictError extends Error {}

/** Names of the content fields in which a retry differs from the stored message. */
export function contentDifferences(stored: MessageContent, retry: MessageContent): string[] {
  return (["toAgent", "body", "threadId"] as const).filter((field) => stored[field] !== retry[field]);
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
