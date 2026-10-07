// agent-relay delivery-state-machine: one place decides how a direct message's delivery state may change (D28).
import type { DatabaseSync } from "node:sqlite";

/**
 * `queued` waits for delivery; `sending` has a wake in flight; `accepted` means the host confirmed the wake or
 * the recipient fetched the message; `failed` is a definite refusal; `unknown` is an unconfirmed submission,
 * never replayed; `expired` passed its queue timeout while still queued, and is never delivered afterwards.
 */
export type DeliveryState = "queued" | "sending" | "accepted" | "failed" | "unknown" | "expired";

const TRANSITIONS: Readonly<Record<DeliveryState, readonly DeliveryState[]>> = {
  queued: ["sending", "accepted", "expired"],
  // `queued` again: the wake could not be submitted yet (recipient offline, busy, or a permission prompt held it).
  sending: ["queued", "accepted", "failed", "unknown"],
  // Evidence only (a late host receipt or the recipient fetching it), never a second delivery.
  unknown: ["accepted"],
  accepted: [],
  failed: [],
  expired: [],
};

/** Default queue timeout (D27): a request nobody fetched within a day is more likely stale than wanted. */
export const DEFAULT_QUEUE_TIMEOUT_MS = 24 * 3_600_000;
export const MIN_QUEUE_TIMEOUT_MS = 60_000;
export const MAX_QUEUE_TIMEOUT_MS = 7 * 24 * 3_600_000;

export class DeliveryTransitionError extends Error {}

/** The bridge-wide queue timeout: `BRIDGE_QUEUE_TIMEOUT_MS` when sane, otherwise the default. */
export function queueTimeoutMs(env: Record<string, string | undefined> = process.env): number {
  const raw = env.BRIDGE_QUEUE_TIMEOUT_MS;
  if (!raw || !/^\d+$/.test(raw)) return DEFAULT_QUEUE_TIMEOUT_MS;
  const value = Number(raw);
  return value >= MIN_QUEUE_TIMEOUT_MS && value <= MAX_QUEUE_TIMEOUT_MS ? value : DEFAULT_QUEUE_TIMEOUT_MS;
}

/** A per-send timeout in whole seconds, between one minute and seven days. */
export function sendTimeoutMs(expiresInSeconds: number | undefined): number {
  if (expiresInSeconds === undefined) return queueTimeoutMs();
  const ms = expiresInSeconds * 1000;
  if (!Number.isInteger(expiresInSeconds) || ms < MIN_QUEUE_TIMEOUT_MS || ms > MAX_QUEUE_TIMEOUT_MS) {
    throw new Error("expiresInSeconds must be a whole number between 60 and 604800");
  }
  return ms;
}

/** Current state; a row written by an older bridge (NULL) reads as `queued`. */
export function deliveryState(db: DatabaseSync, messageId: number): DeliveryState | null {
  const row = db.prepare("SELECT to_agent, delivery_state FROM messages WHERE id = ?").get(messageId) as
    | { to_agent: string; delivery_state: string | null }
    | undefined;
  if (!row || row.to_agent === "*") return null;
  return (row.delivery_state ?? "queued") as DeliveryState;
}

/**
 * Move a direct message to `to`. Returns false when it already is there; throws on a transition the table
 * does not allow. The update is conditional on the state read, so a concurrent writer cannot be overwritten.
 */
export function transition(db: DatabaseSync, messageId: number, to: DeliveryState, now = Date.now()): boolean {
  const from = deliveryState(db, messageId);
  if (from === null) throw new DeliveryTransitionError(`message ${messageId} has no delivery state`);
  if (from === to) return false;
  if (!TRANSITIONS[from].includes(to)) {
    throw new DeliveryTransitionError(`message ${messageId}: ${from} -> ${to} is not allowed`);
  }
  const result = db.prepare(
    `UPDATE messages SET delivery_state = ?, delivery_changed_at = ?
     WHERE id = ? AND COALESCE(delivery_state, 'queued') = ?`,
  ).run(to, now, messageId, from);
  if (Number(result.changes) !== 1) {
    throw new DeliveryTransitionError(`message ${messageId} changed state concurrently`);
  }
  return true;
}
