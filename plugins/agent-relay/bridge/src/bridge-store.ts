import { type DeliveryState, assertBelowPendingCap, atomically, expireDue, sendTimeoutMs } from "./delivery.js";
import { type PendingReason, type WakeDoubt, type WakeJob, WakeQueue, withDoubt } from "./wake-queue.js";
import { assertMayReply, conflictError, contentDifferences, ReplyLinkError, replyThread, RequestCloseError } from "./idempotency.js";
import { DatabaseSync } from "node:sqlite";
import { existsSync, mkdirSync } from "node:fs";
import { basename, dirname, join } from "node:path";

import { DATA_DIR_NAME, ensurePrivateDirectory, restrictToOwner } from "./fs-safety.js";
import { bodyPart, clampLimit, fitMessages, type FitOptions, type MessageView } from "./paging.js";
import { migrate, SCHEMA_VERSION, schemaVersion, type MigrationResult } from "./schema.js";

/**
 * agent-relay awaiting-reply-view D202: an open request (aliased `m`) is a direct message its sender marked
 * expectsReply that has no linked reply, did not fail or expire, and whose recipient is not retired. An
 * acknowledgement does not close it. Only the recipient can link a reply (identity-check). request-closing D216: nor
 * is it closed by a row in `request_closures` (answered through `alsoAnswers`, or withdrawn by its sender).
 */
const OPEN_REQUEST = `m.expects_reply = 1 AND m.to_agent != '*'
  AND COALESCE(m.delivery_state, 'queued') NOT IN ('failed', 'expired')
  AND NOT EXISTS (SELECT 1 FROM messages x WHERE x.reply_to = m.id)
  AND NOT EXISTS (SELECT 1 FROM request_closures rc WHERE rc.request_id = m.id)
  AND NOT EXISTS (SELECT 1 FROM agents ra WHERE ra.name = m.to_agent AND ra.retired_at IS NOT NULL)`;

/** A message as stored and returned by the bridge. */
export interface BridgeMessage {
  id: number;
  fromAgent: string;
  toAgent: string;
  body: string;
  threadId: string | null;
  idempotencyKey: string | null;
  createdAt: string;
  /** agent-relay delivery-state-machine: null for broadcasts. */
  deliveryState: DeliveryState | null;
  /** ISO time after which a still-queued direct message expires; null for broadcasts and older rows. */
  expiresAt: string | null;
  /** agent-relay idempotency: id of the message this one replies to; null when it is not a reply. */
  replyTo: number | null;
  /** agent-relay awaiting-reply-view D201: the sender expects an answer linked by replyTo. */
  expectsReply: boolean;
}

/** A registered agent and its advertised capabilities. */
export interface BridgeAgent {
  name: string;
  capabilities: string[];
  registeredAt: string;
  lastSeen: string;
  retiredAt: string | null;
  retiredBy: string | null;
  retireNote: string | null;
  /** agent-relay identity-check: the host session this name was registered from; null when unknown. */
  host: AgentHost | null;
}

/** A host session: Claude's id is verified from the bridge's environment, Codex's is claimed by the session. */
export interface AgentHost {
  /** script-access D244: `script` is a script identity, owned by no session; only the runtime CLI acts as it. */
  app: "claude" | "codex" | "script";
  sessionId: string;
}

export interface AgentSummary extends BridgeAgent {
  unread: number;
  /** Latest of registration refresh, sent message or acknowledgement. */
  lastActivity: string;
}

export interface SendInput {
  wake?: boolean;
  /** Per-send queue timeout (D27), 60 … 604800 seconds; default from BRIDGE_QUEUE_TIMEOUT_MS or 24 h. */
  expiresInSeconds?: number;
  fromAgent: string;
  toAgent: string;
  body: string;
  threadId?: string | null;
  idempotencyKey?: string | null;
  /** agent-relay idempotency: id of the message this one replies to (it must exist; D36 sets the thread). */
  replyTo?: number | null;
  /** agent-relay awaiting-reply-view D201: mark a direct message as expecting an answer; refused on a broadcast. */
  expectsReply?: boolean;
  /** agent-relay request-closing D217: further open requests addressed to the sender that this message answers. */
  alsoAnswers?: number[];
  /** agent-relay request-closing D219: the sender's own open requests to this recipient that it withdraws. */
  withdraws?: number[];
}

/** agent-relay request-closing D216: how a request was closed other than by a `replyTo` link. */
export type ClosureKind = "answered" | "withdrawn";
export interface Closure { id: number; kind: ClosureKind }
/** request-closing D237, D238: a request named in alsoAnswers or withdraws that was already closed, so it was skipped. */
export type SkipReason = "withdrawn" | "answered" | "failed" | "expired";
export interface Skipped { id: number; reason: SkipReason; by?: number }
type Delivered = { message: BridgeMessage; duplicate: boolean; closed: Closure[]; skipped: Skipped[] };

/** At most this many ids in alsoAnswers or withdraws (D217, D219). */
export const MAX_CLOSURES = 20;

/** request-closing D217, D219: what a list of request ids may look like before any of them is read. */
function closureListShape(field: "alsoAnswers" | "withdraws", ids: number[], toAgent: string): void {
  if (!ids.length) return;
  if (toAgent === "*") {
    throw new RequestCloseError(`A broadcast cannot carry ${field}: send it in a direct message.`);
  }
  if (ids.length > MAX_CLOSURES) throw new RequestCloseError(`${field} takes at most ${MAX_CLOSURES} ids.`);
  const seen = new Set<number>();
  for (const id of ids) {
    if (seen.has(id)) throw new RequestCloseError(`${field} names #${id} twice.`);
    seen.add(id);
  }
}

export interface InboxOptions {
  includeAcknowledged?: boolean;
  /** agent-relay delivery-state-machine: also return messages that expired before delivery (history). */
  includeExpired?: boolean;
  fromAgent?: string;
  threadId?: string;
  afterId?: number;
  limit?: number;
}

export interface InboxPage {
  count: number;
  totalUnread: number;
  hasMore: boolean;
  nextAfterId: number | null;
  messages: MessageView[];
}

export interface ThreadPageOptions extends FitOptions {
  afterId?: number;
  beforeId?: number;
  limit?: number;
}

export interface ThreadPage {
  threadId: string;
  total: number;
  count: number;
  olderBeforeId: number | null;
  newerAfterId: number | null;
  messages: MessageView[];
}

export interface OutboxEntry {
  id: number;
  toAgent: string;
  threadId: string | null;
  createdAt: string;
  preview: string;
  bodyLength: number;
  acknowledgedAt: string | null;
  /** accepted-unread-notice D230: `doubt` while an accepted Codex ping's message stays unread for five minutes. */
  wake: { state: string; detail: string; pendingReason?: PendingReason; doubt?: WakeDoubt } | null;
  recipient: "active" | "retired" | "unknown";
  /** agent-relay delivery-state-machine (D29). */
  deliveryState: DeliveryState;
  expiresAt: string | null;
  /** agent-relay idempotency: the message this one replies to, and the ids of the replies it received. */
  replyTo: number | null;
  replies: number[];
  /** agent-relay request-closing D220: the message that closed this request other than by `replyTo`. */
  closedBy?: { messageId: number; kind: ClosureKind };
  /** agent-relay awaiting-reply-view D203: the sender marked it as expecting an answer. */
  expectsReply: boolean;
  /** Whole seconds since it was sent; only in the awaiting-reply view. */
  waitingSeconds?: number;
}

/** agent-relay ops-commands (D45): where one message stands. */
export type MessageOutcome = "pending" | "acknowledged" | "replied" | "withdrawn" | "failed" | "expired";

export interface MessageStatus {
  message: { id: number; fromAgent: string; toAgent: string; threadId: string | null; createdAt: string;
    preview: string; bodyLength: number; replyTo: number | null };
  deliveryState: DeliveryState | null;
  expiresAt: string | null;
  acknowledgedAt: string | null;
  replies: number[];
  /** agent-relay request-closing D220: the message that closed this request other than by `replyTo`. */
  closedBy?: { messageId: number; kind: ClosureKind };
  /** accepted-unread-notice D230: `doubt` while an accepted Codex ping's message stays unread for five minutes. */
  wake: (WakeJob & { doubt?: WakeDoubt }) | null;
  /** replied, else withdrawn, else acknowledged, else failed or expired, else pending (`unknown` may still resolve). */
  outcome: MessageOutcome;
}

export interface RetireInput {
  by: string;
  note?: string;
  closeBacklog?: boolean;
}

export interface RetireRecord {
  agent: BridgeAgent;
  unbound: boolean;
  closed: number;
  bySender: Array<{ fromAgent: string; count: number; messageIds: number[] }>;
}

export interface BridgeStoreOptions {
  /** Where pre-migration and daily backups go. Defaults to `<db dir>/backups`. */
  backupDir?: string;
  /**
   * agent-relay script-access D242: open the mailbox read-only (SQLite `readOnly`): no migration (a schema other than
   * this runtime's is refused), no expiry sweep, and any write throws. For scripts that only read.
   */
  readOnly?: boolean;
}

/** script-access D242: the mailbox cannot be read as it is (missing, or a schema this runtime does not read). */
export class ReadOnlyMailboxError extends Error {}

/** Wildcard recipient: delivered to every agent except the sender. */
const BROADCAST = "*";

type Param = string | number | null;

interface MessageRow {
  id: number | bigint;
  from_agent: string;
  to_agent: string;
  body: string;
  thread_id: string | null;
  idempotency_key: string | null;
  created_at: string;
  delivery_state?: string | null;
  expires_at?: number | null;
  reply_to?: number | bigint | null;
  expects_reply?: number | bigint | null;
}

interface AgentRow {
  name: string;
  capabilities: string;
  registered_at: string;
  last_seen: string;
  retired_at: string | null;
  retired_by: string | null;
  retire_note: string | null;
  host_app?: string | null;
  host_session?: string | null;
}

/**
 * Delivery rule, used everywhere a message's recipients are decided: direct
 * messages to the agent, plus broadcasts from others sent after it registered
 * (late joiners do not inherit old broadcasts; unregistered readers see all).
 * Placeholder form binds the agent three times.
 */
const DELIVERED_TO = (agentColumn: string) => `
  (m.to_agent = ${agentColumn} OR (
    m.to_agent = '${BROADCAST}' AND m.from_agent != ${agentColumn}
    AND m.created_at >= COALESCE((SELECT registered_at FROM agents r WHERE r.name = ${agentColumn}), '')
  ))`;

const UNREAD_FOR = (agentColumn: string) => `
  ${DELIVERED_TO(agentColumn)}
  AND COALESCE(m.delivery_state, '') != 'expired'
  AND NOT EXISTS (
    SELECT 1 FROM acknowledgements a WHERE a.message_id = m.id AND a.agent = ${agentColumn}
  )`;

/** Bindings for DELIVERED_TO("?") and UNREAD_FOR("?"), which name the agent 3 and 4 times. */
const deliveredParams = (agent: string): Param[] => [agent, agent, agent];
const unreadParams = (agent: string): Param[] => [agent, agent, agent, agent];

function optionalNumber(value: number | bigint | null): number | null {
  return value === null ? null : Number(value);
}

/**
 * SQLite-backed mailbox shared between agents. All state lives in a single
 * database file so multiple processes (Claude, Codex, ...) coordinate through
 * the same store.
 */
export class BridgeStore {
  private readonly db: DatabaseSync;
  readonly wakes: WakeQueue;
  readonly dbPath: string;
  readonly backupDir: string | null;
  readonly migration: MigrationResult;
  readonly readOnly: boolean;

  constructor(dbPath: string, options: BridgeStoreOptions = {}) {
    this.dbPath = dbPath;
    this.readOnly = options.readOnly === true;
    const inMemory = dbPath === ":memory:";
    if (this.readOnly) {
      this.backupDir = null;
      if (inMemory || !existsSync(dbPath)) throw new ReadOnlyMailboxError(`No mailbox at ${dbPath}.`);
      this.db = new DatabaseSync(dbPath, { readOnly: true });
      this.db.exec("PRAGMA busy_timeout = 5000;");
      const version = schemaVersion(this.db);
      if (version !== SCHEMA_VERSION) {
        this.db.close();
        throw new ReadOnlyMailboxError(`The mailbox is at schema ${version}, but this runtime reads schema ${SCHEMA_VERSION}; ` +
          "upgrade or repair the runtime with native_collaboration_runtime.py.");
      }
      this.migration = { from: version, to: version, newer: false };
      this.wakes = new WakeQueue(this.db, dbPath);
      return;
    }
    this.backupDir = inMemory ? null : options.backupDir ?? join(dirname(dbPath), "backups");
    if (!inMemory) {
      const directory = dirname(dbPath);
      // Tighten our own data directory; a caller-chosen directory keeps its mode.
      if (basename(directory) === DATA_DIR_NAME) ensurePrivateDirectory(directory);
      else mkdirSync(directory, { recursive: true, mode: 0o700 });
    }
    this.db = new DatabaseSync(dbPath);
    // agent-relay identity-check (D40): wait for another process's lock before the first statement that needs one.
    this.db.exec("PRAGMA busy_timeout = 5000;");
    this.db.exec("PRAGMA journal_mode = WAL;");
    this.db.exec("PRAGMA foreign_keys = ON;");
    this.migration = migrate(this.db, (from) => this.backupBeforeMigration(from));
    if (!inMemory) this.restrictDatabaseFiles();
    this.wakes = new WakeQueue(this.db, dbPath);
  }

  /** Expire what is due (delivery-state-machine), except on a read-only store (script-access D242). */
  private sweep(): void {
    if (!this.readOnly) expireDue(this.db);
  }

  /** Messages and history are private working data: keep them owner-only. */
  restrictDatabaseFiles(): void {
    for (const suffix of ["", "-wal", "-shm"]) restrictToOwner(`${this.dbPath}${suffix}`);
  }

  private backupBeforeMigration(fromVersion: number): void {
    if (!this.backupDir) return;
    ensurePrivateDirectory(this.backupDir);
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const target = join(
      this.backupDir,
      `bridge-pre-v${SCHEMA_VERSION}-from-v${fromVersion}-${stamp}-${process.pid}.sqlite`,
    );
    try {
      this.backupTo(target);
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      throw new Error(`Refusing to migrate without a backup (${target}): ${reason}`);
    }
  }

  /** Consistent point-in-time copy, safe while other processes write. */
  backupTo(path: string): void {
    this.db.prepare("VACUUM INTO ?").run(path);
    restrictToOwner(path);
  }

  private now(): string {
    return new Date().toISOString();
  }

  private toMessage(row: MessageRow): BridgeMessage {
    return {
      id: Number(row.id),
      fromAgent: row.from_agent,
      toAgent: row.to_agent,
      body: row.body,
      threadId: row.thread_id,
      idempotencyKey: row.idempotency_key,
      createdAt: row.created_at,
      deliveryState: row.to_agent === "*" ? null : ((row.delivery_state ?? "queued") as DeliveryState),
      expiresAt: row.expires_at == null ? null : new Date(Number(row.expires_at)).toISOString(),
      replyTo: row.reply_to == null ? null : Number(row.reply_to),
      expectsReply: Number(row.expects_reply ?? 0) === 1,
    };
  }

  /** The underlying connection, for the delivery module and tests. */
  get database(): DatabaseSync {
    return this.db;
  }

  /**
   * Deliver a message. When an idempotency key is supplied and a message with
   * the same (fromAgent, idempotencyKey) already exists, the original message
   * is returned instead of creating a duplicate.
   */
  send(input: SendInput): BridgeMessage {
    return this.deliver(input).message;
  }

  /**
   * agent-relay idempotency (D33, D34): like `send`, and says whether the result is an already stored message.
   * A reused key with different content is refused, except for the bridge's own notices, which fold by key.
   */
  deliver(input: SendInput): Delivered {
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const result = this.insertMessage(input);
      this.db.exec("COMMIT");
      return result;
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  private insertMessage(input: SendInput): Delivered {
    const replyTo = input.replyTo ?? null;
    const expectsReply = input.expectsReply === true;
    if (expectsReply && input.toAgent === "*") {
      throw new Error("A broadcast cannot carry expectsReply: send the request to one recipient.");
    }
    const alsoAnswers = input.alsoAnswers ?? [];
    closureListShape("alsoAnswers", alsoAnswers, input.toAgent);
    if (replyTo !== null && alsoAnswers.includes(replyTo)) {
      throw new RequestCloseError(`#${replyTo} is also the replyTo; list only the other requests in alsoAnswers.`);
    }
    const withdraws = input.withdraws ?? [];
    closureListShape("withdraws", withdraws, input.toAgent);
    const both = withdraws.find((id) => alsoAnswers.includes(id));
    if (both !== undefined) throw new RequestCloseError(`#${both} is named in both alsoAnswers and withdraws.`);
    let threadId = input.threadId ?? null;
    let answersOwnMessage = false;
    if (replyTo !== null) {
      const original = this.db.prepare("SELECT thread_id, from_agent, to_agent FROM messages WHERE id = ?").get(replyTo) as
        | { thread_id: string | null; from_agent: string; to_agent: string }
        | undefined;
      if (!original) throw new ReplyLinkError(`No message #${replyTo} to reply to.`);
      assertMayReply(replyTo, original.from_agent, original.to_agent, input.fromAgent, original.thread_id);
      threadId = replyThread(replyTo, original.thread_id, input.threadId);
      answersOwnMessage = original.to_agent === input.fromAgent;
    }
    const idempotencyKey = input.idempotencyKey ?? null;

    if (idempotencyKey !== null) {
      // delivery-robustness D264 (review of #161): sweep first, so a request in a retry's lists that has passed its
      // timeout is compared and skipped as expired instead of reading as open (a content conflict), and the stored
      // message reads its own current state.
      this.sweep();
      const existing = this.db
        .prepare("SELECT * FROM messages WHERE from_agent = ? AND idempotency_key = ?")
        .get(input.fromAgent, idempotencyKey) as unknown as MessageRow | undefined;
      if (existing) {
        const stored = this.toMessage(existing);
        // request-closing D217: a retry compares the lists it closed, after which a retry of a send that already
        // closed its requests returns the stored message instead of refusing itself.
        const closed = this.closuresBy(stored.id);
        const differs = contentDifferences(
          { ...stored, alsoAnswers: closed.filter((c) => c.kind === "answered").map((c) => c.id),
            withdraws: closed.filter((c) => c.kind === "withdrawn").map((c) => c.id) },
          { toAgent: input.toAgent, body: input.body, threadId, replyTo, expectsReply,
            alsoAnswers: this.closableBy(alsoAnswers, stored.id), withdraws: this.closableBy(withdraws, stored.id) });
        if (differs.length && input.fromAgent !== "bridge") {
          throw conflictError(idempotencyKey, input.fromAgent, stored.id, stored.deliveryState, differs);
        }
        this.assertListsClosable(alsoAnswers, withdraws, input.fromAgent, input.toAgent);
        return { message: stored, duplicate: true, closed, skipped: this.skippedOnRetry([...alsoAnswers, ...withdraws], stored.id) };
      }
    }

    // agent-relay idempotency (D35): the same reply to the same message is stored once, unless the earlier one
    // never arrived (failed or expired), so a lost reply can be sent again.
    // request-closing (round-2 review of #130): only an earlier reply that closed exactly the same lists folds, so a
    // reply resent to add alsoAnswers or withdraws is stored and checked as a new message instead of being swallowed.
    if (replyTo !== null) {
      this.sweep();
      const candidates = this.db
        .prepare(
          `SELECT * FROM messages WHERE reply_to = ? AND from_agent = ? AND to_agent = ? AND body = ?
             AND COALESCE(delivery_state, 'queued') NOT IN ('failed', 'expired')
           ORDER BY id`,
        )
        .all(replyTo, input.fromAgent, input.toAgent, input.body) as unknown as MessageRow[];
      // Revision D238: an exact match first; only then one whose closures equal the list minus what it skipped.
      for (const lenient of [false, true]) {
        for (const earlier of candidates) {
          const closed = this.closuresBy(Number(earlier.id));
          const same = !contentDifferences(
            { toAgent: "", body: "", threadId: null, replyTo: null, expectsReply: false,
              alsoAnswers: closed.filter((c) => c.kind === "answered").map((c) => c.id),
              withdraws: closed.filter((c) => c.kind === "withdrawn").map((c) => c.id) },
            { toAgent: "", body: "", threadId: null, replyTo: null, expectsReply: false,
              alsoAnswers: lenient ? this.closableBy(alsoAnswers, Number(earlier.id)) : alsoAnswers,
              withdraws: lenient ? this.closableBy(withdraws, Number(earlier.id)) : withdraws }).length;
          if (same) {
            this.assertListsClosable(alsoAnswers, withdraws, input.fromAgent, input.toAgent);
            return { message: this.toMessage(earlier), duplicate: true, closed,
              skipped: this.skippedOnRetry([...alsoAnswers, ...withdraws], Number(earlier.id)) };
          }
        }
      }
    }

    // agent-relay request-closing D217: checked here, inside deliver()'s write transaction and after the idempotent
    // returns, so another bridge process cannot close the same request in between. A request past its timeout is
    // expired first, so it is skipped as expired even when no sweep ran yet (round-2 review of #130).
    // Revision 2026-10-19 D237: a wrong id refuses the whole send; a request already closed is skipped.
    if (alsoAnswers.length || withdraws.length) this.sweep();
    const skipped: Skipped[] = [
      ...alsoAnswers.map((id) => this.assertClosable(id, "answer", input.fromAgent)),
      ...withdraws.map((id) => this.assertClosable(id, "withdraw", input.fromAgent, input.toAgent)),
    ].filter((skip): skip is Skipped => skip !== null);
    const skippedIds = new Set(skipped.map((skip) => skip.id));
    const answering = alsoAnswers.filter((id) => !skippedIds.has(id));
    const withdrawing = withdraws.filter((id) => !skippedIds.has(id));

    const direct = input.toAgent !== "*";
    // agent-relay durable-ordering (D30, D31): after the idempotent return, so a retry of a stored message passes.
    // The bridge's own notices (failure, retirement, results) must always get through.
    if (direct && input.fromAgent !== "bridge") assertBelowPendingCap(this.db, input.toAgent);
    const sentAt = Date.now();
    const expiresAt = direct ? sentAt + sendTimeoutMs(input.expiresInSeconds) : null;
    const result = this.db
      .prepare(
        `INSERT INTO messages (from_agent, to_agent, body, thread_id, idempotency_key, created_at,
                               delivery_state, delivery_changed_at, expires_at, reply_to, expects_reply)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(input.fromAgent, input.toAgent, input.body, threadId, idempotencyKey,
        new Date(sentAt).toISOString(), direct ? "queued" : null, direct ? sentAt : null, expiresAt, replyTo,
        expectsReply ? 1 : 0);

    const message = this.messageById(Number(result.lastInsertRowid)) as BridgeMessage;
    if (input.wake !== false) this.wakes.enqueue(message);
    // agent-relay mailbox-polish D155: the recipient answering a direct message has it, as surely as a fetch.
    if (answersOwnMessage && replyTo !== null) this.wakes.recordRead(input.fromAgent, [replyTo]);
    // D219: a withdrawal is neither an answer nor delivery evidence, so it records no read and sends no notice.
    const closed = [...this.closeRequests(message.id, answering, "answered", skipped),
      ...this.closeRequests(message.id, withdrawing, "withdrawn", skipped)].sort((a, b) => a.id - b.id);
    const answered = closed.filter((c) => c.kind === "answered").map((c) => c.id);
    if (answered.length) {
      this.wakes.recordRead(input.fromAgent, answered);
      this.noticeOtherRequesters(message, answered);
    }
    return { message, duplicate: false, closed, skipped: skipped.sort((a, b) => a.id - b.id) };
  }

  /**
   * request-closing D218: a request closed through alsoAnswers whose sender is not the answer's recipient would never
   * show it the answer. One `bridge` notice per such requester and answer, in the same transaction; it pings like every
   * notice. Retired or unregistered requesters get none.
   */
  private noticeOtherRequesters(answer: BridgeMessage, requestIds: number[]): void {
    const rows = this.db.prepare(`SELECT id, from_agent, thread_id FROM messages WHERE id IN (${requestIds.map(() => "?").join(",")})
      ORDER BY id`).all(...requestIds) as Array<{ id: number | bigint; from_agent: string; thread_id: string | null }>;
    const byRequester = new Map<string, { ids: number[]; threadId: string | null }>();
    for (const row of rows) {
      const requester = row.from_agent;
      if (requester === answer.toAgent || requester === answer.fromAgent || requester === "bridge") continue;
      const agent = this.getAgent(requester);
      if (!agent || agent.retiredAt) continue;
      const entry = byRequester.get(requester) ?? { ids: [], threadId: row.thread_id };
      entry.ids.push(Number(row.id));
      byRequester.set(requester, entry);
    }
    for (const [requester, { ids, threadId }] of byRequester) {
      const which = ids.length === 1 ? `Your request #${ids[0]}` : `Your requests ${ids.map((id) => `#${id}`).join(", ")}`;
      this.insertMessage({
        fromAgent: "bridge",
        toAgent: requester,
        threadId,
        idempotencyKey: `answered:${answer.id}:${requester}`,
        body: [
          `${which} to ${JSON.stringify(answer.fromAgent)} ${ids.length === 1 ? "was" : "were"} answered by #${answer.id} ` +
            `(sent to ${JSON.stringify(answer.toAgent)}).`,
          `Read it with bridge_inbox {agent: ${JSON.stringify(requester)}, messageId: ${answer.id}}. Preview: ` +
            answer.body.slice(0, 280),
          "This is an automated bridge notice. Do not reply to it.",
        ].join("\n\n"),
      });
    }
  }

  /** request-closing D222: the requests a message closed other than by `replyTo`, in id order. */
  private closuresBy(messageId: number): Closure[] {
    return (this.db.prepare("SELECT request_id, kind FROM request_closures WHERE message_id = ? ORDER BY request_id")
      .all(messageId) as Array<{ request_id: number | bigint; kind: ClosureKind }>)
      .map((row) => ({ id: Number(row.request_id), kind: row.kind }));
  }

  /**
   * request-closing D217, D219: refuse, naming the id, a request that `sender` may not close as `role`, or that is no
   * longer open. Runs inside the send's transaction.
   */
  /**
   * request-closing D217, D219; revision D237: an id that names the wrong message throws, the whole send refused; a
   * request that is already closed returns its skip.
   */
  private assertClosable(id: number, role: "answer" | "withdraw", sender: string, recipient?: string): Skipped | null {
    const refuse = (why: string) => new RequestCloseError(`Cannot close request #${id}: ${why}. Nothing was sent.`);
    const row = this.db.prepare("SELECT from_agent, to_agent, expects_reply, delivery_state FROM messages WHERE id = ?")
      .get(id) as { from_agent: string; to_agent: string; expects_reply: number | bigint; delivery_state: string | null } | undefined;
    if (!row) throw refuse(`there is no message #${id}`);
    if (role === "answer" && row.to_agent !== sender) throw refuse(`it is addressed to "${row.to_agent}", not to "${sender}"`);
    if (role === "withdraw" && row.from_agent !== sender) throw refuse(`it was sent by "${row.from_agent}", not by "${sender}"`);
    if (role === "withdraw" && row.to_agent !== recipient) {
      throw refuse(`it is addressed to "${row.to_agent}"; send the withdrawal to "${row.to_agent}"`);
    }
    if (Number(row.expects_reply) !== 1) throw refuse("it is not a request (it was not sent with expectsReply)");
    return this.closedState(id, row.delivery_state);
  }

  /**
   * Review of #161: a retry refuses an id that a new send would refuse (no message, wrong addressee or sender, not a
   * request), even when that id is closed elsewhere and so left out of the comparison and listed by skippedOnRetry.
   */
  private assertListsClosable(alsoAnswers: number[], withdraws: number[], sender: string, recipient: string): void {
    for (const id of alsoAnswers) this.assertClosable(id, "answer", sender);
    for (const id of withdraws) this.assertClosable(id, "withdraw", sender, recipient);
  }

  /** D237: how a request is already closed (a closure, a replyTo answer, failed, expired), or null while it is open. */
  private closedState(id: number, deliveryState?: string | null): Skipped | null {
    const closure = this.db.prepare("SELECT message_id, kind FROM request_closures WHERE request_id = ?").get(id) as
      { message_id: number | bigint; kind: ClosureKind } | undefined;
    if (closure) return { id, reason: closure.kind, by: Number(closure.message_id) };
    const reply = this.db.prepare("SELECT MIN(id) AS id FROM messages WHERE reply_to = ?").get(id) as { id: number | bigint | null };
    if (reply.id !== null) return { id, reason: "answered", by: Number(reply.id) };
    const state = deliveryState !== undefined ? deliveryState
      : (this.db.prepare("SELECT delivery_state FROM messages WHERE id = ?").get(id) as { delivery_state: string | null } | undefined)
        ?.delivery_state;
    if (state === "failed" || state === "expired") return { id, reason: state };
    return null;
  }

  /**
   * D238: the ids of a retried list that a stored message could still have closed — those open, or closed by that
   * message itself — so a retry of a send that skipped a request still matches the stored message.
   */
  private closableBy(ids: number[], storedId: number): number[] {
    return ids.filter((id) => {
      const state = this.closedState(id);
      return state === null || state.by === storedId;
    });
  }

  /**
   * post-090-bridge D253 (revises D238): on a duplicate return, the ids of the retried lists that the stored message
   * did not close and that are closed now, so the sender sees each id in `closed` or `skipped`. Nothing is stored.
   */
  private skippedOnRetry(ids: number[], storedId: number): Skipped[] {
    return [...new Set(ids)].map((id) => this.closedState(id))
      .filter((state): state is Skipped => state !== null && state.by !== storedId)
      .sort((x, y) => x.id - y.id);
  }

  /** request-closing D216: one closure row per request; revision D237: a lost race is added to `skipped`. */
  private closeRequests(messageId: number, ids: number[], kind: ClosureKind, skipped: Skipped[]): Closure[] {
    const insert = this.db.prepare("INSERT INTO request_closures (request_id, message_id, kind, closed_at) VALUES (?, ?, ?, ?)");
    const now = this.now();
    const closed: Closure[] = [];
    for (const id of ids) {
      try {
        insert.run(id, messageId, kind, now);
        closed.push({ id, kind });
      } catch (error) {
        if (!/constraint/i.test(String((error as Error).message))) throw error;
        const other = this.db.prepare("SELECT message_id, kind FROM request_closures WHERE request_id = ?").get(id) as
          { message_id: number | bigint; kind: ClosureKind } | undefined;
        // post-090-bridge D254: a constraint other than the one closure per request leaves no row to report.
        if (!other) {
          throw new Error(`Could not close request #${id} with message #${messageId}, and no closure is recorded for it: ` +
            (error as Error).message);
        }
        skipped.push({ id, reason: other.kind, by: Number(other.message_id) });
      }
    }
    return closed;
  }

  /** agent-relay ops-commands (D45): the status of one message, or undefined when it does not exist. */
  messageStatus(id: number): MessageStatus | undefined {
    this.sweep();
    const message = this.messageById(id);
    if (!message) return undefined;
    const ack = this.db.prepare("SELECT acked_at FROM acknowledgements WHERE message_id = ? AND agent = ?")
      .get(id, message.toAgent) as { acked_at: string } | undefined;
    const replies = (this.db.prepare(`SELECT id FROM messages WHERE reply_to = ?
      UNION SELECT message_id FROM request_closures WHERE request_id = ? AND kind = 'answered' ORDER BY 1`)
      .all(id, id) as Array<{ id: number | bigint }>).map((row) => Number(row.id));
    const acknowledgedAt = ack?.acked_at ?? null;
    const closure = this.db.prepare("SELECT message_id, kind FROM request_closures WHERE request_id = ?").get(id) as
      { message_id: number | bigint; kind: ClosureKind } | undefined;
    // request-closing D220: a reply wins over a withdrawal; closedBy keeps what was recorded.
    const outcome: MessageOutcome = replies.length ? "replied"
      : closure?.kind === "withdrawn" ? "withdrawn"
      : acknowledgedAt ? "acknowledged"
      : message.deliveryState === "failed" ? "failed"
      : message.deliveryState === "expired" ? "expired"
      : "pending";
    return {
      message: { id, fromAgent: message.fromAgent, toAgent: message.toAgent, threadId: message.threadId,
        createdAt: message.createdAt, preview: message.body.slice(0, 200), bodyLength: message.body.length,
        replyTo: message.replyTo },
      deliveryState: message.deliveryState,
      expiresAt: message.expiresAt,
      acknowledgedAt,
      replies,
      ...(closure ? { closedBy: { messageId: Number(closure.message_id), kind: closure.kind } } : {}),
      wake: wakeWithDoubt(this.wakes.forMessage(id), this.wakes.doubts().get(id)),
      outcome,
    };
  }

  messageById(id: number): BridgeMessage | undefined {
    const row = this.db.prepare("SELECT * FROM messages WHERE id = ?").get(id) as unknown as
      | MessageRow
      | undefined;
    return row ? this.toMessage(row) : undefined;
  }

  /**
   * Messages addressed to `agent` (directly or by broadcast), oldest first.
   * Unacknowledged only unless `includeAcknowledged`. Broadcasts never appear
   * in the sender's own inbox.
   */
  inbox(agent: string, options: InboxOptions = {}): BridgeMessage[] {
    this.sweep();
    const clauses = [DELIVERED_TO("?")];
    const params: Param[] = deliveredParams(agent);
    if (!options.includeExpired) clauses.push("COALESCE(m.delivery_state, '') != 'expired'");
    if (!options.includeAcknowledged) {
      clauses.push(
        "NOT EXISTS (SELECT 1 FROM acknowledgements a WHERE a.message_id = m.id AND a.agent = ?)",
      );
      params.push(agent);
    }
    if (options.fromAgent) {
      clauses.push("m.from_agent = ?");
      params.push(options.fromAgent);
    }
    if (options.threadId) {
      clauses.push("m.thread_id = ?");
      params.push(options.threadId);
    }
    if (options.afterId !== undefined) {
      clauses.push("m.id > ?");
      params.push(options.afterId);
    }
    let sql = `SELECT m.* FROM messages m WHERE ${clauses.join(" AND ")} ORDER BY m.id ASC`;
    if (options.limit !== undefined) {
      sql += " LIMIT ?";
      params.push(options.limit);
    }
    const rows = this.db.prepare(sql).all(...params) as unknown as MessageRow[];
    return rows.map((row) => this.toMessage(row));
  }

  countUnread(agent: string): number {
    this.sweep();
    const row = this.db
      .prepare(`SELECT COUNT(*) AS n FROM messages m WHERE ${UNREAD_FOR("?")}`)
      .get(...unreadParams(agent)) as { n: number | bigint };
    return Number(row.n);
  }

  /** A bounded inbox read that always fits comfortably inside an MCP result. */
  inboxPage(agent: string, options: InboxOptions & FitOptions = {}): InboxPage {
    const limit = clampLimit(options.limit);
    const rows = this.inbox(agent, { ...options, limit: limit + 1 });
    const fitted = fitMessages(rows.slice(0, limit), options);
    const hasMore = rows.length > limit || fitted.omitted > 0;
    const last = fitted.messages.at(-1);
    return {
      count: fitted.messages.length,
      totalUnread: this.countUnread(agent),
      hasMore,
      nextAfterId: hasMore && last ? last.id : null,
      messages: fitted.messages,
    };
  }

  /**
   * agent-relay long-messages D152: one message delivered to `agent`, with the part of its body from `bodyOffset` that
   * fits a page. Undefined when the message is not in that agent's inbox (same rule as inbox()).
   */
  messagePart(agent: string, messageId: number, options: { bodyOffset?: number; maxChars?: number } = {}):
    (MessageView & { direction: "received" | "sent" | "answer" }) | undefined {
    // agent-relay read-own-sent D212: also a message `agent` sent; delivered to it wins (a message to oneself).
    // request-closing D218: also an answer that closed one of `agent`'s requests through alsoAnswers.
    const answered = `EXISTS (SELECT 1 FROM request_closures rc JOIN messages q ON q.id = rc.request_id
      WHERE rc.message_id = m.id AND rc.kind = 'answered' AND q.from_agent = ?)`;
    const row = this.db.prepare(`SELECT m.*, CASE WHEN ${DELIVERED_TO("?")} THEN 'received' WHEN m.from_agent = ? THEN 'sent'
      ELSE 'answer' END AS direction
      FROM messages m WHERE m.id = ? AND (${DELIVERED_TO("?")} OR m.from_agent = ? OR ${answered})`)
      .get(...deliveredParams(agent), agent, messageId, ...deliveredParams(agent), agent, agent) as
      unknown as (MessageRow & { direction: "received" | "sent" | "answer" }) | undefined;
    return row ? { ...bodyPart(this.toMessage(row), options.bodyOffset ?? 0, options.maxChars), direction: row.direction } : undefined;
  }

  /** read-own-sent D213: who sent and received a message, to word a refused read; undefined when there is none. */
  messageParties(messageId: number): { from: string; to: string } | undefined {
    const row = this.db.prepare("SELECT from_agent, to_agent FROM messages WHERE id = ?").get(messageId) as
      { from_agent: string; to_agent: string } | undefined;
    return row ? { from: row.from_agent, to: row.to_agent } : undefined;
  }

  /**
   * Mark messages as acknowledged by `agent`. Returns the number of messages
   * newly acknowledged (already-acknowledged ids are ignored).
   */
  ack(agent: string, messageIds: number[], note: string | null = null): number {
    // Only messages actually delivered to this agent may be acknowledged:
    // a direct message addressed to it, or a broadcast it did not send. The
    // guard mirrors the delivery rule in inbox().
    const stmt = this.db.prepare(
      `INSERT OR IGNORE INTO acknowledgements (message_id, agent, acked_at, note)
       SELECT m.id, ?, ?, ?
       FROM messages m
       WHERE m.id = ? AND ${DELIVERED_TO("?")}`,
    );
    // agent-relay ack-records-read D197: handling a message (for example from its wake preview) is also reading it,
    // so a newly acknowledged direct message gets read_at if it had none; an earlier read time is kept.
    const read = this.db.prepare("UPDATE messages SET read_at = COALESCE(read_at, ?) WHERE id = ? AND to_agent = ?");
    const ackedAt = this.now();
    // agent-relay ack-wake-atomic D130: every acknowledgement and its wake closure commit together, or none does,
    // so an acknowledged message never keeps an open wake job that could ping its recipient again.
    return atomically(this.db, () => {
      let acknowledged = 0;
      for (const id of messageIds) {
        const result = stmt.run(agent, ackedAt, note, id, ...deliveredParams(agent));
        acknowledged += Number(result.changes);
        if (Number(result.changes) === 1) {
          read.run(Date.now(), id, agent);
          this.wakes.acknowledge(agent, id);
        }
      }
      return acknowledged;
    });
  }

  /** All messages in a conversation thread, oldest first. */
  thread(threadId: string): BridgeMessage[] {
    const rows = this.db
      .prepare("SELECT * FROM messages WHERE thread_id = ? ORDER BY id ASC")
      .all(threadId) as unknown as MessageRow[];
    return rows.map((row) => this.toMessage(row));
  }

  /**
   * One page of a thread. Without a cursor it returns the most recent
   * messages; `beforeId` pages backwards and `afterId` pages forwards.
   */
  threadPage(threadId: string, options: ThreadPageOptions = {}): ThreadPage {
    const limit = clampLimit(options.limit, 30);
    let messages: MessageView[];
    if (options.afterId !== undefined) {
      const rows = this.db
        .prepare("SELECT * FROM messages WHERE thread_id = ? AND id > ? ORDER BY id ASC LIMIT ?")
        .all(threadId, options.afterId, limit) as unknown as MessageRow[];
      messages = fitMessages(rows.map((row) => this.toMessage(row)), options).messages;
    } else {
      const before = options.beforeId ?? Number.MAX_SAFE_INTEGER;
      const rows = this.db
        .prepare("SELECT * FROM messages WHERE thread_id = ? AND id < ? ORDER BY id DESC LIMIT ?")
        .all(threadId, before, limit) as unknown as MessageRow[];
      // Spend the budget on the newest messages, then present oldest first.
      messages = fitMessages(rows.map((row) => this.toMessage(row)), options).messages.reverse();
    }
    const exists = (sql: string, id: number) =>
      this.db.prepare(sql).get(threadId, id) !== undefined;
    const first = messages[0];
    const last = messages.at(-1);
    const total = this.db
      .prepare("SELECT COUNT(*) AS n FROM messages WHERE thread_id = ?")
      .get(threadId) as { n: number | bigint };
    return {
      threadId,
      total: Number(total.n),
      count: messages.length,
      olderBeforeId:
        first && exists("SELECT 1 FROM messages WHERE thread_id = ? AND id < ? LIMIT 1", first.id)
          ? first.id
          : null,
      newerAfterId:
        last && exists("SELECT 1 FROM messages WHERE thread_id = ? AND id > ? LIMIT 1", last.id)
          ? last.id
          : null,
      messages,
    };
  }

  /**
   * Direct messages `agent` sent, newest first, with the recipient's handling state. awaiting-reply-view D203: with
   * `awaitingReply`, only its open requests (D202), oldest first, acknowledged or not, each with the seconds waited.
   */
  outbox(
    agent: string,
    options: { includeAcknowledged?: boolean; limit?: number; awaitingReply?: boolean; now?: number } = {},
  ): { totalUnacknowledged: number; totalAwaitingReply: number; hasMore: boolean; entries: OutboxEntry[] } {
    const limit = clampLimit(options.limit, 30);
    const awaitingReply = options.awaitingReply === true;
    const filter = awaitingReply ? `AND ${OPEN_REQUEST}` : options.includeAcknowledged ? "" : "AND a.acked_at IS NULL";
    const now = options.now ?? Date.now();
    this.sweep();
    const doubts = this.wakes.doubts(now);
    const rows = this.db
      .prepare(
        `SELECT m.id, m.to_agent, m.thread_id, m.created_at, substr(m.body, 1, 200) AS preview,
                length(m.body) AS body_length, a.acked_at, w.state AS wake_state,
                w.detail AS wake_detail, r.name AS recipient_name, r.retired_at AS recipient_retired,
                CASE WHEN w.state = 'pending' THEN COALESCE(w.pending_reason, (
                  SELECT o.pending_reason FROM wake_jobs o WHERE o.agent = w.agent
                    AND o.state IN ('pending', 'sending') AND o.pending_reason IS NOT NULL ORDER BY o.id LIMIT 1))
                END AS wake_reason,
                m.delivery_state, m.expires_at, m.reply_to, m.expects_reply,
                (SELECT json_group_array(id) FROM (SELECT x.id AS id FROM messages x WHERE x.reply_to = m.id
                  UNION SELECT rc.message_id FROM request_closures rc WHERE rc.request_id = m.id AND rc.kind = 'answered'
                  ORDER BY id)) AS replies,
                (SELECT json_object('messageId', rc.message_id, 'kind', rc.kind) FROM request_closures rc
                  WHERE rc.request_id = m.id) AS closed_by
         FROM messages m
         LEFT JOIN acknowledgements a ON a.message_id = m.id AND a.agent = m.to_agent
         LEFT JOIN wake_jobs w ON w.message_id = m.id AND w.agent = m.to_agent
         LEFT JOIN agents r ON r.name = m.to_agent
         WHERE m.from_agent = ? AND m.to_agent != ? ${filter}
         ORDER BY m.id ${awaitingReply ? "ASC" : "DESC"} LIMIT ?`,
      )
      .all(agent, BROADCAST, limit + 1) as Array<Record<string, string | number | bigint | null>>;
    const total = this.db
      .prepare(
        `SELECT COUNT(*) AS n FROM messages m
         WHERE m.from_agent = ? AND m.to_agent != ? AND NOT EXISTS (
           SELECT 1 FROM acknowledgements a WHERE a.message_id = m.id AND a.agent = m.to_agent
         )`,
      )
      .get(agent, BROADCAST) as { n: number | bigint };
    const open = this.db
      .prepare(`SELECT COUNT(*) AS n FROM messages m WHERE m.from_agent = ? AND ${OPEN_REQUEST}`)
      .get(agent) as { n: number | bigint };
    return {
      totalUnacknowledged: Number(total.n),
      totalAwaitingReply: Number(open.n),
      hasMore: rows.length > limit,
      entries: rows.slice(0, limit).map((row) => ({
        id: Number(row.id),
        toAgent: row.to_agent as string,
        threadId: row.thread_id as string | null,
        createdAt: row.created_at as string,
        preview: row.preview as string,
        bodyLength: Number(row.body_length),
        acknowledgedAt: row.acked_at as string | null,
        wake:
          row.wake_state === null
            ? null
            : withDoubt({
              state: row.wake_state as string, detail: row.wake_detail as string,
              // claude-offline-notice D193: why a pending ping waits; a message queued behind an earlier one to the
              // same recipient waits for that one's reason.
              ...(row.wake_reason == null ? {} : { pendingReason: row.wake_reason as PendingReason }),
            }, doubts.get(Number(row.id))),
        recipient:
          row.recipient_name === null ? "unknown" : row.recipient_retired ? "retired" : "active",
        deliveryState: ((row.delivery_state as string | null) ?? "queued") as DeliveryState,
        expiresAt: row.expires_at == null ? null : new Date(Number(row.expires_at)).toISOString(),
        replyTo: row.reply_to == null ? null : Number(row.reply_to),
        replies: JSON.parse(row.replies as string) as number[],
        ...(row.closed_by == null ? {} : { closedBy: JSON.parse(row.closed_by as string) as { messageId: number; kind: ClosureKind } }),
        expectsReply: Number(row.expects_reply ?? 0) === 1,
        ...(awaitingReply
          ? { waitingSeconds: Math.max(0, Math.floor((now - Date.parse(row.created_at as string)) / 1000)) }
          : {}),
      })),
    };
  }

  /**
   * agent-relay script-access D244: record `name` as a script identity (host `script`, no wake binding). Registering
   * an existing script identity again changes nothing; a name held by a session, or retired, is refused.
   */
  registerScriptIdentity(name: string): BridgeAgent {
    const existing = this.getAgent(name);
    if (existing?.retiredAt) {
      throw new Error(`"${name}" was retired at ${existing.retiredAt}; choose another name for the script identity.`);
    }
    if (existing?.host?.app === "script") return existing;
    if (existing) {
      const holder = existing.host ? `a ${existing.host.app} session` : "a session";
      throw new Error(`"${name}" is registered by ${holder}; a script identity needs a name of its own.`);
    }
    return this.register(name, [], { app: "script", sessionId: name });
  }

  /**
   * Register or refresh an agent's presence. Omitted capabilities keep the
   * existing list. Registering again reactivates a retired agent; bridge_register allows that only with
   * reactivate: true (agent-relay cleanup-gaps D61).
   */
  register(name: string, capabilities?: string[], host?: AgentHost | null): BridgeAgent {
    const now = this.now();
    const existing = this.getAgent(name);
    const serialized = JSON.stringify(capabilities ?? existing?.capabilities ?? []);
    // agent-relay identity-check: a given host is recorded, `undefined` keeps the recorded one, `null` clears it.
    this.db
      .prepare(
        `INSERT INTO agents (name, capabilities, registered_at, last_seen, host_app, host_session)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(name) DO UPDATE SET
           capabilities = excluded.capabilities,
           last_seen = excluded.last_seen,
           host_app = CASE WHEN ? THEN excluded.host_app ELSE COALESCE(excluded.host_app, agents.host_app) END,
           host_session = CASE WHEN ? THEN excluded.host_session ELSE COALESCE(excluded.host_session, agents.host_session) END,
           retired_at = NULL, retired_by = NULL, retire_note = NULL`,
      )
      .run(name, serialized, now, now, host?.app ?? null, host?.sessionId ?? null, host === null ? 1 : 0, host === null ? 1 : 0);
    return this.getAgent(name) as BridgeAgent;
  }

  getAgent(name: string): BridgeAgent | undefined {
    const row = this.db.prepare("SELECT * FROM agents WHERE name = ?").get(name) as unknown as
      | AgentRow
      | undefined;
    return row ? this.toAgent(row) : undefined;
  }

  /** Record activity for a registered agent. Unknown names are ignored. */
  touch(name: string): void {
    this.db.prepare("UPDATE agents SET last_seen = ? WHERE name = ?").run(this.now(), name);
  }

  /** Latest of registration refresh, sent message or acknowledgement, if registered. */
  lastActivity(name: string): string | null {
    const row = this.db
      .prepare(
        `SELECT MAX(ag.last_seen,
             COALESCE((SELECT MAX(created_at) FROM messages WHERE from_agent = ag.name), ''),
             COALESCE((SELECT MAX(acked_at) FROM acknowledgements WHERE agent = ag.name), '')
           ) AS last_activity
         FROM agents ag WHERE ag.name = ?`,
      )
      .get(name) as { last_activity: string } | undefined;
    return row?.last_activity ?? null;
  }

  private toAgent(row: AgentRow): BridgeAgent {
    return {
      name: row.name,
      capabilities: JSON.parse(row.capabilities) as string[],
      registeredAt: row.registered_at,
      lastSeen: row.last_seen,
      retiredAt: row.retired_at ?? null,
      retiredBy: row.retired_by ?? null,
      retireNote: row.retire_note ?? null,
      host: row.host_app && row.host_session
        ? { app: row.host_app as AgentHost["app"], sessionId: row.host_session }
        : null,
    };
  }

  /** Registered agents in registration order. Retired agents are hidden by default. */
  agents(options: { includeRetired?: boolean } = {}): BridgeAgent[] {
    const filter = options.includeRetired ? "" : "WHERE retired_at IS NULL";
    const rows = this.db
      .prepare(`SELECT * FROM agents ${filter} ORDER BY registered_at ASC, name ASC`)
      .all() as unknown as AgentRow[];
    return rows.map((row) => this.toAgent(row));
  }

  /** Agents with unread counts and their latest observable activity. */
  agentSummaries(options: { includeRetired?: boolean } = {}): AgentSummary[] {
    const filter = options.includeRetired ? "" : "WHERE ag.retired_at IS NULL";
    const rows = this.db
      .prepare(
        `SELECT ag.*,
           (SELECT COUNT(*) FROM messages m WHERE ${UNREAD_FOR("ag.name")}) AS unread,
           MAX(ag.last_seen,
               COALESCE((SELECT MAX(created_at) FROM messages WHERE from_agent = ag.name), ''),
               COALESCE((SELECT MAX(acked_at) FROM acknowledgements WHERE agent = ag.name), '')
           ) AS last_activity
         FROM agents ag ${filter}
         ORDER BY ag.registered_at ASC, ag.name ASC`,
      )
      .all() as unknown as Array<AgentRow & { unread: number | bigint; last_activity: string }>;
    return rows.map((row) => ({
      ...this.toAgent(row),
      unread: Number(row.unread),
      lastActivity: row.last_activity,
    }));
  }

  /**
   * agent-relay acceptance-030-gaps D77: direct messages waiting for each non-retired agent (not acknowledged by it,
   * not failed or expired), oldest first: count, senders and at most 20 ids, never bodies. waiting-list-all-hosts
   * D198: for every host, not only Codex, and with the oldest one's creation time (`oldestAt`).
   */
  waiting(): Map<string, { count: number; from: string[]; ids: number[]; oldestAt: string; doubtfulIds?: number[] }> {
    const rows = this.db
      .prepare(
        `SELECT m.id, m.from_agent, m.to_agent, m.created_at FROM messages m JOIN agents ag ON ag.name = m.to_agent
         WHERE ag.retired_at IS NULL
           AND COALESCE(m.delivery_state, 'queued') NOT IN ('failed', 'expired')
           AND NOT EXISTS (SELECT 1 FROM acknowledgements a WHERE a.message_id = m.id AND a.agent = m.to_agent)
         ORDER BY m.to_agent, m.id`,
      )
      .all() as Array<{ id: number | bigint; from_agent: string; to_agent: string; created_at: string }>;
    const waiting = new Map<string, { count: number; from: string[]; ids: number[]; oldestAt: string; doubtfulIds?: number[] }>();
    for (const row of rows) {
      const entry = waiting.get(row.to_agent) ?? { count: 0, from: [], ids: [], oldestAt: row.created_at };
      entry.count += 1;
      if (!entry.from.includes(row.from_agent)) entry.from.push(row.from_agent);
      if (entry.ids.length < 20) entry.ids.push(Number(row.id));
      waiting.set(row.to_agent, entry);
    }
    // accepted-unread-notice D230: the waiting messages whose accepted Codex ping went unread, oldest first, at most 20.
    for (const doubt of this.wakes.acceptedUnread()) {
      const entry = waiting.get(doubt.agent);
      if (!entry) continue;
      entry.doubtfulIds ??= [];
      if (entry.doubtfulIds.length < 20) entry.doubtfulIds.push(doubt.messageId);
    }
    return waiting;
  }

  /**
   * agent-relay awaiting-reply-view D204: per recipient, the open requests (D202) addressed to it — what others wait
   * for it to answer. Retired recipients never appear (OPEN_REQUEST leaves them out).
   */
  owesReplies(): Map<string, { count: number; ids: number[]; oldestAt: string }> {
    const rows = this.db
      .prepare(`SELECT m.id, m.to_agent, m.created_at FROM messages m WHERE ${OPEN_REQUEST} ORDER BY m.to_agent, m.id`)
      .all() as Array<{ id: number | bigint; to_agent: string; created_at: string }>;
    const owes = new Map<string, { count: number; ids: number[]; oldestAt: string }>();
    for (const row of rows) {
      const entry = owes.get(row.to_agent) ?? { count: 0, ids: [], oldestAt: row.created_at };
      entry.count += 1;
      if (entry.ids.length < 20) entry.ids.push(Number(row.id));
      owes.set(row.to_agent, entry);
    }
    return owes;
  }

  /**
   * agent-relay presence-and-approval D148: per Claude agent, its oldest direct message not yet handled, with the
   * session to check. Retired agents and failed or expired messages are left out. presence-polish D176: only agents
   * bound to wake a Claude session, the sessions the bridge already watches (no background reading of the others).
   */
  claudeWaiting(): Array<{ agent: string; sessionId: string; messageId: number; fromAgent: string }> {
    const rows = this.db
      .prepare(
        `SELECT m.id, m.from_agent, m.to_agent, ag.host_app, ag.host_session,
                json_extract(w.target, '$.app') AS wake_app, json_extract(w.target, '$.sessionId') AS wake_session
         FROM messages m JOIN agents ag ON ag.name = m.to_agent JOIN wake_targets w ON w.agent = ag.name
         WHERE ag.retired_at IS NULL
           AND json_extract(w.target, '$.app') = 'claude'
           AND COALESCE(m.delivery_state, 'queued') NOT IN ('failed', 'expired')
           AND NOT EXISTS (SELECT 1 FROM acknowledgements a WHERE a.message_id = m.id AND a.agent = m.to_agent)
           AND m.id = (SELECT MIN(m2.id) FROM messages m2 WHERE m2.to_agent = m.to_agent
             AND COALESCE(m2.delivery_state, 'queued') NOT IN ('failed', 'expired')
             AND NOT EXISTS (SELECT 1 FROM acknowledgements a2 WHERE a2.message_id = m2.id AND a2.agent = m2.to_agent))
         ORDER BY m.to_agent`,
      )
      .all() as Array<{ id: number | bigint; from_agent: string; to_agent: string; host_app: string | null;
        host_session: string | null; wake_app: string | null; wake_session: string | null }>;
    return rows.flatMap((row) => {
      const sessionId = row.wake_session;
      return sessionId ? [{ agent: row.to_agent, sessionId, messageId: Number(row.id), fromAgent: row.from_agent }] : [];
    });
  }

  /**
   * Retire an agent: stop pings, and optionally close its unhandled backlog.
   * Closed messages keep their history; the acknowledgement records why.
   */
  retire(name: string, input: RetireInput): RetireRecord {
    const agent = this.getAgent(name);
    if (!agent) throw new Error(`Unknown agent: ${name}`);
    const closeBacklog = input.closeBacklog ?? true;
    const now = this.now();
    const note = `Closed unhandled when ${name} was retired by ${input.by}${input.note ? `: ${input.note}` : ""}`;
    this.db.exec("BEGIN IMMEDIATE");
    try {
      this.db
        .prepare("UPDATE agents SET retired_at = ?, retired_by = ?, retire_note = ? WHERE name = ?")
        .run(now, input.by, input.note ?? null, name);
      const unbound = this.wakes.target(name) !== null;
      if (unbound) this.wakes.bind(name, null);
      const backlog = closeBacklog
        ? (this.db
            .prepare(`SELECT m.id, m.from_agent FROM messages m WHERE ${UNREAD_FOR("?")} ORDER BY m.id`)
            .all(...unreadParams(name)) as Array<{ id: number | bigint; from_agent: string }>)
        : [];
      const close = this.db.prepare(
        "INSERT OR IGNORE INTO acknowledgements (message_id, agent, acked_at, note) VALUES (?, ?, ?, ?)",
      );
      const bySender = new Map<string, number[]>();
      for (const row of backlog) {
        close.run(Number(row.id), name, now, note);
        bySender.set(row.from_agent, [...(bySender.get(row.from_agent) ?? []), Number(row.id)]);
      }
      this.db.exec("COMMIT");
      return {
        agent: this.getAgent(name) as BridgeAgent,
        unbound,
        closed: backlog.length,
        bySender: [...bySender].map(([fromAgent, messageIds]) => ({
          fromAgent,
          count: messageIds.length,
          messageIds,
        })),
      };
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  getMeta(key: string): string | null {
    const row = this.db.prepare("SELECT value FROM meta WHERE key = ?").get(key) as
      | { value: string }
      | undefined;
    return row?.value ?? null;
  }

  setMeta(key: string, value: string): void {
    this.db
      .prepare(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
      )
      .run(key, value);
  }

  /**
   * Cross-process "at most once per interval" claim. Returns true for exactly
   * one caller per interval, even when several bridge processes race.
   */
  claimInterval(key: string, intervalMs: number, now = Date.now()): boolean {
    const row = this.db
      .prepare(
        `INSERT INTO meta (key, value) VALUES (?, ?)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value
         WHERE CAST(meta.value AS INTEGER) <= ?
         RETURNING value`,
      )
      .get(key, String(now), now - intervalMs);
    return row !== undefined;
  }

  /** Background ping outcomes per app and state since a point in time. */
  wakeSummary(sinceMs: number): Array<{ app: string; state: string; count: number }> {
    const rows = this.db
      .prepare(
        `SELECT json_extract(target, '$.app') AS app, state, COUNT(*) AS n
         FROM wake_jobs WHERE created_at >= ? GROUP BY app, state ORDER BY app, n DESC`,
      )
      .all(sinceMs) as Array<{ app: string; state: string; n: number | bigint }>;
    return rows.map((row) => ({ app: row.app, state: row.state, count: Number(row.n) }));
  }

  quickCheck(): string {
    const row = this.db.prepare("PRAGMA quick_check").get() as { quick_check: string };
    return row.quick_check;
  }

  close(): void {
    this.db.close();
  }
}

/** accepted-unread-notice D230: a message status's wake job, marked while its delivery is doubtful. */
function wakeWithDoubt(job: WakeJob | null, acceptedAt: number | undefined): (WakeJob & { doubt?: WakeDoubt }) | null {
  return job ? withDoubt(job, acceptedAt) : null;
}
