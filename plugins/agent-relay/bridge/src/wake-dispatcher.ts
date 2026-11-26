import type { BridgeMessage, BridgeStore } from "./bridge-store.js";
import { channelNotification, type ChannelNotification } from "./claude-channel.js";
import { ClaudeWake, claudeNotRunning, claudeSessionsOrNull, type ClaudeSession } from "./claude-wake.js";
import { CODEX_NOT_LOADED, wakeCodex } from "./codex-wake.js";
import { claudeLocation, type Location } from "./location.js";
import { noticeAcceptedUnread } from "./notices.js";
import { BUSY_NOTIFY_AFTER_MS, CLAUDE_OFFLINE_NOTIFY_AFTER_MS, NOTIFIED_TEXT, alreadyNotified, noticesOff, notifyUndelivered,
  waitingEpisode } from "./notify.js";
import { claudePresence, type Presence } from "./presence.js";
import { IDLE_HOLD_EXPIRY_MARGIN_MS, parseProcStart, type WakeJob, type WakeResult } from "./wake-queue.js";

/** Push path into the Claude session hosting this MCP process (opt-in). */
export interface ChannelDelivery {
  sessionId: string;
  send(notification: ChannelNotification): Promise<void>;
}

export interface DispatcherOptions {
  deliver?: (job: WakeJob) => Promise<WakeResult>;
  channel?: ChannelDelivery | null;
  /** Environment for notifications and idle holding; defaults to this process's. */
  env?: NodeJS.ProcessEnv;
  /** Injectable for tests. */
  codexWake?: (job: WakeJob) => Promise<WakeResult>;
  /** presence-and-approval D148: a Claude session's state by session id; defaults to Claude Code's registry. */
  presenceOf?: (sessionId: string) => Promise<Presence>;
  /** notice-location D188: where a waiting Claude session is; defaults to the registry entry `presenceOf` came from. */
  locationOf?: (sessionId: string) => Promise<Location | undefined>;
  /** rewake-on-return D199: the live Claude sessions; defaults to Claude Code's registry. */
  claudeSessions?: () => Promise<ClaudeSession[] | null>;
  idleHoldMs?: number;
  now?: () => number;
}

/**
 * Why a Codex ping that did not get through is told to the user (D67), busy aside. codex-not-loaded D200: a task the app
 * did not answer for is usually one the user has not opened yet, so the notice says to open it.
 */
export function codexNoticeReason(result: WakeResult): string | null {
  if (result.state === "held") return "Codex could not be woken; the message waits";
  if (result.state !== "pending") return null;
  return result.detail === CODEX_NOT_LOADED ? "this Codex task is not open; open it in the ChatGPT app"
    : "Codex is not running; the message waits";
}

/** How often a bridge looks for Claude sessions waiting for the user's approval (D148). */
export const APPROVAL_CHECK_MS = 30_000;

const DEFAULT_IDLE_HOLD_MS = 3_600_000;

/** idle-wake-batching D304: a whole number of ms in range, or zero to disable holding. */
export function idleHoldMs(env: Record<string, string | undefined> = process.env): number {
  const raw = env.BRIDGE_IDLE_HOLD_MS;
  if (raw === "0") return 0;
  if (!raw || !/^\d+$/.test(raw)) return DEFAULT_IDLE_HOLD_MS;
  const value = Number(raw);
  return value >= 60_000 && value <= 86_400_000 ? value : DEFAULT_IDLE_HOLD_MS;
}

export function findSession(sessions: ClaudeSession[] | null, sessionId: string): ClaudeSession | undefined {
  return sessions?.find(s => s.sessionId === sessionId || s.bridgeSessionId === sessionId);
}

function idleMinutes(session: Pick<ClaudeSession, "status" | "statusUpdatedAt"> | undefined,
  thresholdMs: number, now: number): number | null {
  const since = session?.statusUpdatedAt;
  if (session?.status !== "idle" || since === undefined || !Number.isFinite(since)) return null;
  const elapsed = now - since;
  return elapsed >= thresholdMs ? Math.floor(elapsed / 60_000) : null;
}

/** idle-wake-batching D299: the idle minutes when a ping may wait. */
export function idleHoldReason(job: Pick<WakeJob, "target" | "explicitWake" | "released">,
  message: Pick<BridgeMessage, "expectsReply" | "expiresAt"> | undefined,
  session: Pick<ClaudeSession, "status" | "statusUpdatedAt"> | undefined, thresholdMs: number, now: number): number | null {
  if (job.target.app !== "claude" || !message || message.expectsReply || job.explicitWake || job.released
    || !(thresholdMs > 0)) return null;
  if (message.expiresAt !== null && !(Date.parse(message.expiresAt) - now > IDLE_HOLD_EXPIRY_MARGIN_MS)) return null;
  return idleMinutes(session, thresholdMs, now);
}

/** Review of #164 (D267): how often, and how far apart, a late Claude receipt's write is tried; well inside the hold grace. */
const LATE_RECEIPT_TRIES = 5;
export const LATE_RECEIPT_RETRY_MS = 2_000;

export class WakeDispatcher {
  private running: Promise<void> | null = null;
  private stopped = false;
  private timer: NodeJS.Timeout | null = null;
  private claude: ClaudeWake;
  private deliver?: (job: WakeJob) => Promise<WakeResult>;
  private channel: ChannelDelivery | null;
  private env: NodeJS.ProcessEnv;
  private codexWake: (job: WakeJob) => Promise<WakeResult>;
  private presenceOf?: (sessionId: string) => Promise<Presence>;
  private locationOf?: (sessionId: string) => Promise<Location | undefined>;
  private claudeSessions?: () => Promise<ClaudeSession[] | null>;
  private idleHoldMs: number;
  private now: () => number;
  private periodicCheckedAt = 0;
  private readClaudeSessions = (): Promise<ClaudeSession[] | null> => (this.claudeSessions ?? claudeSessionsOrNull)();

  constructor(private store: BridgeStore, options: DispatcherOptions | ((job: WakeJob) => Promise<WakeResult>) = {}) {
    const resolved = typeof options === "function" ? { deliver: options } : options;
    this.deliver = resolved.deliver;
    this.channel = resolved.channel ?? null;
    this.env = resolved.env ?? process.env;
    this.codexWake = resolved.codexWake ?? ((job) => wakeCodex(job));
    this.presenceOf = resolved.presenceOf;
    this.locationOf = resolved.locationOf;
    this.claudeSessions = resolved.claudeSessions;
    this.idleHoldMs = resolved.idleHoldMs ?? idleHoldMs(this.env);
    this.now = resolved.now ?? Date.now;
    this.claude = new ClaudeWake((job, result) => this.lateReceipt(job, result),
      (agent) => claudeNotRunning(agent, this.store.getAgent(agent)?.desktop));
  }

  /**
   * A Claude receipt that came after its wake returned (a release after a hold, most often). Review of #164 (D267): a
   * busy database is tried again a few times, so a released hold is not left `held` to be announced 90 s later.
   */
  lateReceipt(job: WakeJob, result: WakeResult, tries = 0): void {
    try {
      this.store.wakes.finish(job, result, this.now());
    } catch {
      if (this.stopped || tries + 1 >= LATE_RECEIPT_TRIES) return;
      setTimeout(() => this.lateReceipt(job, result, tries + 1), LATE_RECEIPT_RETRY_MS).unref();
    }
  }

  start(): void {
    // idle-wake-batching D303d: a disabled bridge opens the queue for all existing holds.
    if (this.idleHoldMs === 0) {
      const now = this.now();
      const agents = new Set(this.store.wakes.heldAgents().map(entry => entry.agent));
      for (const agent of agents) this.store.wakes.releaseHeld(agent, "idle holding is disabled", now);
    }
    this.heartbeat();
    this.timer = setInterval(() => {
      this.heartbeat();
      void this.flush().catch(() => {});
      const now = this.now();
      if (now - this.periodicCheckedAt >= APPROVAL_CHECK_MS) {
        this.periodicCheckedAt = now;
        try { this.checkAcceptedUnread(); } catch { /* next check */ }
        // idle-wake-batching D303: use the same registry snapshot and release holds before checking notices.
        let sessions: Promise<ClaudeSession[] | null> | undefined;
        const readOnce = () => sessions ??= this.readClaudeSessions();
        void this.checkHeld(readOnce).catch(() => {}).then(() => this.checkApprovals(readOnce)).catch(() => {});
      }
    }, 2000);
    this.timer.unref();
    void this.flush().catch(() => {});
  }

  private heartbeat(): void {
    if (this.channel && !this.stopped) {
      try { this.store.wakes.heartbeatChannel(this.channel.sessionId); } catch { /* retried next tick */ }
    }
  }

  flush(): Promise<void> {
    if (this.stopped) return Promise.resolve();
    if (this.running) return this.running;
    this.running = this.drain().finally(() => { this.running = null; });
    return this.running;
  }

  private async drain(): Promise<void> {
    if (!this.stopped) {
      // agent-relay delivery-robustness D261: a busy database is a round with nothing to do; the timer tries again.
      let job: WakeJob | null;
      try {
        job = this.store.wakes.claim(this.now());
      } catch {
        return;
      }
      if (!job) return;
      // idle-wake-batching review: a failed read or write here never costs a claimed ping; it is sent as today.
      try {
        const message = job.target.app === "claude" && this.idleHoldMs > 0 && !job.explicitWake && !job.released
          ? this.store.messageById(job.messageId) : undefined;
        // Only a ping that could be held reads the registry (D299: expectsReply, explicit and released never hold).
        if (message && !message.expectsReply) {
          const sessions = await this.readClaudeSessions().catch(() => null);
          // The registry read gives another process time to acknowledge, fetch or reclaim this job.
          const active = this.store.wakes.forMessage(job.messageId);
          if (active?.state !== "sending" || active.attemptId !== job.attemptId) return;
          const minutes = idleHoldReason(job, message,
            findSession(sessions, job.target.sessionId), this.idleHoldMs, this.now());
          if (minutes !== null) {
            // idle-wake-batching D301/D306: no dispatch or notices for a hold.
            this.store.wakes.holdIdle(job, `Held, not sent: ${job.agent}'s Claude session has been idle for ${minutes} min; ` +
              "the ping goes out with its next wake, when the session is active again, or an hour before the message expires.");
            return;
          }
        }
      } catch { /* ping as today */ }
      // D303b, best effort: a release that cannot be written leaves the holds for the next periodic check.
      try { this.store.wakes.releaseHeld(job.agent, "another ping for this recipient went out", this.now()); } catch { /* next check */ }
      let result: WakeResult;
      try {
        result = await this.dispatch(job);
      } catch {
        result = { state: "unknown", detail: "Unexpected adapter failure; check the recipient before retrying" };
      }
      try {
        if (job.target.app === "codex") result = this.noticeUndelivered(job, result);
        else result = this.noticeClaudeOffline(job, result);
        this.store.wakes.finish(job, result, this.now());
      } catch {
        // D261: the job stays `sending`; once its retry time passes, claim() records it `unknown` (never replayed).
      }
    }
  }

  /** agent-relay codex-gated-wake D67: held or offline at once, busy after ten minutes; once per message. */
  private noticeUndelivered(job: WakeJob, result: WakeResult, now = Date.now()): WakeResult {
    const why = result.state === "pending" && result.reason === "busy"
      ? (now - job.createdAt >= BUSY_NOTIFY_AFTER_MS ? "Codex has been busy for ten minutes" : null)
      : codexNoticeReason(result);
    if (!why) return result.state === "pending" ? this.keepNotified(job, result, false, String(job.messageId)) : result;
    // notice-location D188: "busy" is the Codex app answering on its own socket that it holds this thread; in every
    // other case nothing confirms where the Codex side is, so the notice says only "Codex" and has no click action.
    const where: Location = { place: { kind: result.reason === "busy" ? "codex-app" : "codex" } };
    const notified = notifyUndelivered(job.mailboxPath,
      { messageId: job.messageId, fromAgent: job.fromAgent, agent: job.agent, why,
        body: this.store.messageById(job.messageId)?.body, where }, this.env);
    return this.keepNotified(job, result, notified, String(job.messageId));
  }

  /**
   * claude-offline-notice D193: a Claude recipient with no running session (the Claude app stops idle sessions, and only
   * a live process can take a ping) is told to the user once per offline spell, after five minutes from its first
   * waiting message. The spell is keyed by that message, so a later spell — after the session took its messages —
   * gets a new key. Never the message text, never a click.
   */
  private noticeClaudeOffline(job: WakeJob, result: WakeResult, now = Date.now()): WakeResult {
    // claude-offline-notice-fixes D194: only an explicit "offline"; a running but unreachable session is not told.
    if (result.state !== "pending" || result.reason !== "offline") return result;
    const waiting = this.store.wakes.waiting(job.agent);
    if (!waiting || now - waiting.first.createdAt < CLAUDE_OFFLINE_NOTIFY_AFTER_MS) return result;
    const key = `claude-offline-${job.agent}-${waiting.first.messageId}`;
    const notified = notifyUndelivered(job.mailboxPath,
      { kind: "offline", messageId: waiting.first.messageId, fromAgent: waiting.first.fromAgent ?? undefined,
        agent: job.agent, why: "not running", count: waiting.count, since: waiting.first.createdAt, key,
        desktop: this.store.getAgent(job.agent)?.desktop }, this.env);
    return this.keepNotified(job, result, notified, key);
  }

  /**
   * claude-offline-notice-fixes D194: a retry overwrites the wake detail, so every retry after the notice — not only
   * the one that sent it — says that a notice was attempted. Never a second notice.
   */
  private keepNotified(job: WakeJob, result: WakeResult, notified: boolean, key: string): WakeResult {
    return notified || alreadyNotified(job.mailboxPath, key) ? { ...result, detail: `${result.detail} ${NOTIFIED_TEXT}` } : result;
  }

  /**
   * rewake-on-return D199: a live Claude session whose process started after a recipient's pings expired came back,
   * so those still-unhandled messages are pinged once more. A re-armed ping is younger than that process, so the
   * same start never re-arms twice. procStart is UTC text (see parseProcStart).
   */
  private rewakeReturned(waiting: Array<{ agent: string; sessionId: string }>, sessions: ClaudeSession[] | null): void {
    if (!sessions) return;
    for (const entry of waiting) {
      const found = findSession(sessions, entry.sessionId);
      const started = found ? parseProcStart(found.procStart) : null;
      if (started === null) continue;
      try { this.store.wakes.rearm(entry.agent, this.store.wakes.target(entry.agent), started); } catch { /* next check */ }
    }
  }

  /**
   * accepted-unread-notice D229, D230: a Codex ping the app accepted five minutes ago whose message is still unread may
   * have reached a task whose mailbox connection is closed. Tell the user (once per message, the `notified/` mark) and
   * the sender (once, the idempotency key). Every bridge on the mailbox may run this.
   */
  checkAcceptedUnread(now = Date.now()): void {
    if (this.stopped) return;
    for (const entry of this.store.wakes.acceptedUnread(now)) {
      notifyUndelivered(this.store.dbPath, { kind: "accepted-unread", messageId: entry.messageId, fromAgent: entry.fromAgent,
        agent: entry.agent, why: "accepted but not read", since: entry.acceptedAt,
        body: this.store.messageById(entry.messageId)?.body, key: `accepted-unread-${entry.messageId}` }, this.env);
      noticeAcceptedUnread(this.store, entry);
    }
  }

  /** idle-wake-batching D303a/c: release on activity, stop, or an approaching message expiry. */
  async checkHeld(readSessions = this.readClaudeSessions): Promise<void> {
    if (this.stopped || this.idleHoldMs === 0) return;
    const held = this.store.wakes.heldAgents();
    if (held.length === 0) return;
    const sessions = await readSessions().catch(() => null);
    if (this.stopped) return;
    const now = this.now();
    const nearExpiry = this.store.wakes.heldAgentsNearExpiry(now);
    for (const { agent, sessionId } of held) {
      if (nearExpiry.has(agent)) {
        this.store.wakes.releaseHeld(agent, "a held message is within an hour of expiry", now);
      } else if (sessions && idleMinutes(findSession(sessions, sessionId), this.idleHoldMs, now) === null) {
        this.store.wakes.releaseHeld(agent, "the Claude session is no longer idle past the threshold", now);
      }
    }
  }

  /**
   * agent-relay presence-and-approval D148: tell the user, once per waiting episode, that a Claude session with an
   * unhandled message waits for their approval. Only tells; never answers the prompt. Every bridge on the mailbox may
   * run this; the notice mark under `notified/` keeps it to one notice.
   */
  async checkApprovals(readSessions = this.readClaudeSessions): Promise<void> {
    if (this.stopped) return;
    const waiting = this.store.claudeWaiting();
    if (waiting.length === 0) return;
    // Without an injected presence, one registry read serves both the presence and the location (D188): the tty is
    // looked up only for an entry that passed the reader's own liveness check.
    const sessions = this.claudeSessions || !this.presenceOf ? await readSessions() : null;
    this.rewakeReturned(waiting, sessions);
    const presenceOf = this.presenceOf ?? (async (sessionId: string) => claudePresence(sessionId, sessions));
    const locationOf = this.locationOf ?? (async (sessionId: string) => {
      const found = findSession(sessions, sessionId);
      return found ? claudeLocation(found) : undefined;
    });
    for (const entry of waiting) {
      const presence = await presenceOf(entry.sessionId);
      const waiting = presence.state === "waiting-approval";
      // presence-polish D175: without Claude Code's own status time, the episode is keyed by when a bridge first saw it
      // and by the waiting message (nothing ends that episode once the message is handled and the session leaves this
      // list, so a later message must not be hidden behind it).
      const episode = presence.since ?? waitingEpisode(this.store.dbPath, entry.sessionId, waiting);
      if (!waiting || episode === null) continue;
      const key = `approval-${entry.sessionId}-${presence.since ?? `${episode}-${entry.messageId}`}`;
      // No tty or parent lookups for a notice already shown, or when notices are off (no mark is ever written then).
      if (noticesOff(this.store.dbPath, this.env) || alreadyNotified(this.store.dbPath, key)) continue;
      notifyUndelivered(this.store.dbPath, { kind: "approval", messageId: entry.messageId, fromAgent: entry.fromAgent,
        agent: entry.agent, why: "waiting for your approval in its Claude session",
        where: await locationOf(entry.sessionId).catch(() => undefined),
        key }, this.env);
    }
  }

  private async dispatch(job: WakeJob): Promise<WakeResult> {
    if (this.deliver) return this.deliver(job);
    if (this.channel && job.target.app === "claude" && job.target.sessionId === this.channel.sessionId) {
      await this.channel.send(channelNotification(job));
      // Claude Code sends no receipt for channel events; an inbox read marks it read.
      return { state: "unknown", detail: "Pushed to this Claude Code session's channel; Claude Code returns no receipt. No automatic replay." };
    }
    // agent-relay wake-any-mode D140, D141: no gate before the wake and no check after it.
    if (job.target.app === "codex") return this.codexWake(job);
    return this.claude.wake(job);
  }

  async close(): Promise<void> {
    this.stopped = true;
    if (this.timer) clearInterval(this.timer);
    await this.running;
    if (this.channel) {
      try { this.store.wakes.releaseChannel(this.channel.sessionId); } catch { /* store may be closing */ }
    }
    await this.claude.close();
  }
}
