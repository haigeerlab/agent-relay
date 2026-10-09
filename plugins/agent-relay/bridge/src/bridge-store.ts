import { type DeliveryState, assertBelowPendingCap, atomically, expireDue, sendTimeoutMs } from "./delivery.js";
import { type WakeJob, WakeQueue } from "./wake-queue.js";
import { assertMayReply, conflictError, contentDifferences, ReplyLinkError, replyThread } from "./idempotency.js";
import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { basename, dirname, join } from "node:path";

import { DATA_DIR_NAME, ensurePrivateDirectory, restrictToOwner } from "./fs-safety.js";
import { bodyPart, clampLimit, fitMessages, type FitOptions, type MessageView } from "./paging.js";
import { migrate, SCHEMA_VERSION, type MigrationResult } from "./schema.js";

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
  app: "claude" | "codex";
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
  wake: { state: string; detail: string } | null;
  recipient: "active" | "retired" | "unknown";
  /** agent-relay delivery-state-machine (D29). */
  deliveryState: DeliveryState;
  expiresAt: string | null;
  /** agent-relay idempotency: the message this one replies to, and the ids of the replies it received. */
  replyTo: number | null;
  replies: number[];
}

/** agent-relay ops-commands (D45): where one message stands. */
export type MessageOutcome = "pending" | "acknowledged" | "replied" | "failed" | "expired";

export interface MessageStatus {
  message: { id: number; fromAgent: string; toAgent: string; threadId: string | null; createdAt: string;
    preview: string; bodyLength: number; replyTo: number | null };
  deliveryState: DeliveryState | null;
  expiresAt: string | null;
  acknowledgedAt: string | null;
  replies: number[];
  wake: WakeJob | null;
  /** replied, else acknowledged, else failed or expired, else pending (`unknown` may still resolve by evidence). */
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
}

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

  constructor(dbPath: string, options: BridgeStoreOptions = {}) {
    this.dbPath = dbPath;
    const inMemory = dbPath === ":memory:";
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
  deliver(input: SendInput): { message: BridgeMessage; duplicate: boolean } {
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

  private insertMessage(input: SendInput): { message: BridgeMessage; duplicate: boolean } {
    const replyTo = input.replyTo ?? null;
    let threadId = input.threadId ?? null;
    let answersOwnMessage = false;
    if (replyTo !== null) {
      const original = this.db.prepare("SELECT thread_id, from_agent, to_agent FROM messages WHERE id = ?").get(replyTo) as
        | { thread_id: string | null; from_agent: string; to_agent: string }
        | undefined;
      if (!original) throw new ReplyLinkError(`No message #${replyTo} to reply to.`);
      assertMayReply(replyTo, original.from_agent, original.to_agent, input.fromAgent);
      threadId = replyThread(replyTo, original.thread_id, input.threadId);
      answersOwnMessage = original.to_agent === input.fromAgent;
    }
    const idempotencyKey = input.idempotencyKey ?? null;

    if (idempotencyKey !== null) {
      const existing = this.db
        .prepare("SELECT * FROM messages WHERE from_agent = ? AND idempotency_key = ?")
        .get(input.fromAgent, idempotencyKey) as unknown as MessageRow | undefined;
      if (existing) {
        const stored = this.toMessage(existing);
        const differs = contentDifferences(stored, { toAgent: input.toAgent, body: input.body, threadId, replyTo });
        if (differs.length && input.fromAgent !== "bridge") {
          throw conflictError(idempotencyKey, input.fromAgent, stored.id, stored.deliveryState, differs);
        }
        return { message: stored, duplicate: true };
      }
    }

    // agent-relay idempotency (D35): the same reply to the same message is stored once, unless the earlier one
    // never arrived (failed or expired), so a lost reply can be sent again.
    if (replyTo !== null) {
      expireDue(this.db);
      const earlier = this.db
        .prepare(
          `SELECT * FROM messages WHERE reply_to = ? AND from_agent = ? AND to_agent = ? AND body = ?
             AND COALESCE(delivery_state, 'queued') NOT IN ('failed', 'expired')
           ORDER BY id LIMIT 1`,
        )
        .get(replyTo, input.fromAgent, input.toAgent, input.body) as unknown as MessageRow | undefined;
      if (earlier) return { message: this.toMessage(earlier), duplicate: true };
    }

    const direct = input.toAgent !== "*";
    // agent-relay durable-ordering (D30, D31): after the idempotent return, so a retry of a stored message passes.
    // The bridge's own notices (failure, retirement, results) must always get through.
    if (direct && input.fromAgent !== "bridge") assertBelowPendingCap(this.db, input.toAgent);
    const sentAt = Date.now();
    const expiresAt = direct ? sentAt + sendTimeoutMs(input.expiresInSeconds) : null;
    const result = this.db
      .prepare(
        `INSERT INTO messages (from_agent, to_agent, body, thread_id, idempotency_key, created_at,
                               delivery_state, delivery_changed_at, expires_at, reply_to)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .run(input.fromAgent, input.toAgent, input.body, threadId, idempotencyKey,
        new Date(sentAt).toISOString(), direct ? "queued" : null, direct ? sentAt : null, expiresAt, replyTo);

    const message = this.messageById(Number(result.lastInsertRowid)) as BridgeMessage;
    if (input.wake !== false) this.wakes.enqueue(message);
    // agent-relay mailbox-polish D155: the recipient answering a direct message has it, as surely as a fetch.
    if (answersOwnMessage && replyTo !== null) this.wakes.recordRead(input.fromAgent, [replyTo]);
    return { message, duplicate: false };
  }

  /** agent-relay ops-commands (D45): the status of one message, or undefined when it does not exist. */
  messageStatus(id: number): MessageStatus | undefined {
    expireDue(this.db);
    const message = this.messageById(id);
    if (!message) return undefined;
    const ack = this.db.prepare("SELECT acked_at FROM acknowledgements WHERE message_id = ? AND agent = ?")
      .get(id, message.toAgent) as { acked_at: string } | undefined;
    const replies = (this.db.prepare("SELECT id FROM messages WHERE reply_to = ? ORDER BY id").all(id) as Array<{ id: number | bigint }>)
      .map((row) => Number(row.id));
    const acknowledgedAt = ack?.acked_at ?? null;
    const outcome: MessageOutcome = replies.length ? "replied"
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
      wake: this.wakes.forMessage(id),
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
    expireDue(this.db);
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
    expireDue(this.db);
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
  messagePart(agent: string, messageId: number, options: { bodyOffset?: number; maxChars?: number } = {}): MessageView | undefined {
    const row = this.db.prepare(`SELECT m.* FROM messages m WHERE m.id = ? AND ${DELIVERED_TO("?")}`)
      .get(messageId, ...deliveredParams(agent)) as unknown as MessageRow | undefined;
    return row ? bodyPart(this.toMessage(row), options.bodyOffset ?? 0, options.maxChars) : undefined;
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
    const ackedAt = this.now();
    // agent-relay ack-wake-atomic D130: every acknowledgement and its wake closure commit together, or none does,
    // so an acknowledged message never keeps an open wake job that could ping its recipient again.
    return atomically(this.db, () => {
      let acknowledged = 0;
      for (const id of messageIds) {
        const result = stmt.run(agent, ackedAt, note, id, ...deliveredParams(agent));
        acknowledged += Number(result.changes);
        if (Number(result.changes) === 1) this.wakes.acknowledge(agent, id);
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

  /** Direct messages `agent` sent, newest first, with the recipient's handling state. */
  outbox(
    agent: string,
    options: { includeAcknowledged?: boolean; limit?: number } = {},
  ): { totalUnacknowledged: number; hasMore: boolean; entries: OutboxEntry[] } {
    const limit = clampLimit(options.limit, 30);
    const ackFilter = options.includeAcknowledged ? "" : "AND a.acked_at IS NULL";
    expireDue(this.db);
    const rows = this.db
      .prepare(
        `SELECT m.id, m.to_agent, m.thread_id, m.created_at, substr(m.body, 1, 200) AS preview,
                length(m.body) AS body_length, a.acked_at, w.state AS wake_state,
                w.detail AS wake_detail, r.name AS recipient_name, r.retired_at AS recipient_retired,
                m.delivery_state, m.expires_at, m.reply_to,
                (SELECT json_group_array(id) FROM (SELECT x.id FROM messages x WHERE x.reply_to = m.id ORDER BY x.id))
                  AS replies
         FROM messages m
         LEFT JOIN acknowledgements a ON a.message_id = m.id AND a.agent = m.to_agent
         LEFT JOIN wake_jobs w ON w.message_id = m.id AND w.agent = m.to_agent
         LEFT JOIN agents r ON r.name = m.to_agent
         WHERE m.from_agent = ? AND m.to_agent != ? ${ackFilter}
         ORDER BY m.id DESC LIMIT ?`,
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
    return {
      totalUnacknowledged: Number(total.n),
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
            : { state: row.wake_state as string, detail: row.wake_detail as string },
        recipient:
          row.recipient_name === null ? "unknown" : row.recipient_retired ? "retired" : "active",
        deliveryState: ((row.delivery_state as string | null) ?? "queued") as DeliveryState,
        expiresAt: row.expires_at == null ? null : new Date(Number(row.expires_at)).toISOString(),
        replyTo: row.reply_to == null ? null : Number(row.reply_to),
        replies: JSON.parse(row.replies as string) as number[],
      })),
    };
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
   * agent-relay acceptance-030-gaps D77: direct messages waiting for each non-retired agent whose recorded host is
   * Codex (not acknowledged by it, not failed or expired), oldest first: count, senders and at most 20 ids, never bodies.
   */
  codexWaiting(): Map<string, { count: number; from: string[]; ids: number[] }> {
    const rows = this.db
      .prepare(
        `SELECT m.id, m.from_agent, m.to_agent FROM messages m JOIN agents ag ON ag.name = m.to_agent
         WHERE ag.host_app = 'codex' AND ag.retired_at IS NULL
           AND COALESCE(m.delivery_state, 'queued') NOT IN ('failed', 'expired')
           AND NOT EXISTS (SELECT 1 FROM acknowledgements a WHERE a.message_id = m.id AND a.agent = m.to_agent)
         ORDER BY m.to_agent, m.id`,
      )
      .all() as Array<{ id: number | bigint; from_agent: string; to_agent: string }>;
    const waiting = new Map<string, { count: number; from: string[]; ids: number[] }>();
    for (const row of rows) {
      const entry = waiting.get(row.to_agent) ?? { count: 0, from: [], ids: [] };
      entry.count += 1;
      if (!entry.from.includes(row.from_agent)) entry.from.push(row.from_agent);
      if (entry.ids.length < 20) entry.ids.push(Number(row.id));
      waiting.set(row.to_agent, entry);
    }
    return waiting;
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
