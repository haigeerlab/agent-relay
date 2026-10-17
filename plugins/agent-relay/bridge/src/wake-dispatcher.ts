import type { BridgeStore } from "./bridge-store.js";
import { channelNotification, type ChannelNotification } from "./claude-channel.js";
import { ClaudeWake, claudeSessionsOrNull, type ClaudeSession } from "./claude-wake.js";
import { CODEX_NOT_LOADED, wakeCodex } from "./codex-wake.js";
import { claudeLocation, type Location } from "./location.js";
import { noticeAcceptedUnread } from "./notices.js";
import { BUSY_NOTIFY_AFTER_MS, CLAUDE_OFFLINE_NOTIFY_AFTER_MS, NOTIFIED_TEXT, alreadyNotified, noticesOff, notifyUndelivered,
  waitingEpisode } from "./notify.js";
import { claudePresence, type Presence } from "./presence.js";
import { parseProcStart, type WakeJob, type WakeResult } from "./wake-queue.js";

/** Push path into the Claude session hosting this MCP process (opt-in). */
export interface ChannelDelivery {
  sessionId: string;
  send(notification: ChannelNotification): Promise<void>;
}

export interface DispatcherOptions {
  deliver?: (job: WakeJob) => Promise<WakeResult>;
  channel?: ChannelDelivery | null;
  /** Environment for notifications; defaults to this process's. */
  env?: NodeJS.ProcessEnv;
  /** Injectable for tests. */
  codexWake?: (job: WakeJob) => Promise<WakeResult>;
  /** presence-and-approval D148: a Claude session's state by session id; defaults to Claude Code's registry. */
  presenceOf?: (sessionId: string) => Promise<Presence>;
  /** notice-location D188: where a waiting Claude session is; defaults to the registry entry `presenceOf` came from. */
  locationOf?: (sessionId: string) => Promise<Location | undefined>;
  /** rewake-on-return D199: the live Claude sessions; defaults to Claude Code's registry. */
  claudeSessions?: () => Promise<ClaudeSession[] | null>;
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
  private approvalsCheckedAt = 0;

  constructor(private store: BridgeStore, options: DispatcherOptions | ((job: WakeJob) => Promise<WakeResult>) = {}) {
    const resolved = typeof options === "function" ? { deliver: options } : options;
    this.deliver = resolved.deliver;
    this.channel = resolved.channel ?? null;
    this.env = resolved.env ?? process.env;
    this.codexWake = resolved.codexWake ?? ((job) => wakeCodex(job));
    this.presenceOf = resolved.presenceOf;
    this.locationOf = resolved.locationOf;
    this.claudeSessions = resolved.claudeSessions;
    this.claude = new ClaudeWake((job, result) => store.wakes.finish(job, result));
  }

  start(): void {
    this.heartbeat();
    this.timer = setInterval(() => {
      this.heartbeat();
      void this.flush().catch(() => {});
      if (Date.now() - this.approvalsCheckedAt >= APPROVAL_CHECK_MS) {
        try { this.checkAcceptedUnread(); } catch { /* next check */ }
        void this.checkApprovals().catch(() => {});
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
      const job = this.store.wakes.claim();
      if (!job) return;
      let result: WakeResult;
      try {
        result = await this.dispatch(job);
      } catch {
        result = { state: "unknown", detail: "Unexpected adapter failure; check the recipient before retrying" };
      }
      if (job.target.app === "codex") result = this.noticeUndelivered(job, result);
      else result = this.noticeClaudeOffline(job, result);
      this.store.wakes.finish(job, result);
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
        agent: job.agent, why: "not running", count: waiting.count, since: waiting.first.createdAt, key }, this.env);
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
      const found = sessions.find((s) => s.sessionId === entry.sessionId || s.bridgeSessionId === entry.sessionId);
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

  /**
   * agent-relay presence-and-approval D148: tell the user, once per waiting episode, that a Claude session with an
   * unhandled message waits for their approval. Only tells; never answers the prompt. Every bridge on the mailbox may
   * run this; the notice mark under `notified/` keeps it to one notice.
   */
  async checkApprovals(): Promise<void> {
    this.approvalsCheckedAt = Date.now();
    if (this.stopped) return;
    const waiting = this.store.claudeWaiting();
    if (waiting.length === 0) return;
    // Without an injected presence, one registry read serves both the presence and the location (D188): the tty is
    // looked up only for an entry that passed the reader's own liveness check.
    const sessions = this.claudeSessions ? await this.claudeSessions()
      : this.presenceOf ? null : await claudeSessionsOrNull();
    this.rewakeReturned(waiting, sessions);
    const presenceOf = this.presenceOf ?? (async (sessionId: string) => claudePresence(sessionId, sessions));
    const locationOf = this.locationOf ?? (async (sessionId: string) => {
      const found = sessions?.find((s) => s.sessionId === sessionId || s.bridgeSessionId === sessionId);
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
