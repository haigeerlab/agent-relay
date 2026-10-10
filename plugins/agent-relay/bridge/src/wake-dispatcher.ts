import type { BridgeStore } from "./bridge-store.js";
import { channelNotification, type ChannelNotification } from "./claude-channel.js";
import { ClaudeWake, claudeSessionsOrNull } from "./claude-wake.js";
import { wakeCodex } from "./codex-wake.js";
import { claudeLocation, type Location } from "./location.js";
import { BUSY_NOTIFY_AFTER_MS, NOTIFIED_TEXT, alreadyNotified, noticesOff, notifyUndelivered, waitingEpisode } from "./notify.js";
import { claudePresence, type Presence } from "./presence.js";
import type { WakeJob, WakeResult } from "./wake-queue.js";

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
  private approvalsCheckedAt = 0;

  constructor(private store: BridgeStore, options: DispatcherOptions | ((job: WakeJob) => Promise<WakeResult>) = {}) {
    const resolved = typeof options === "function" ? { deliver: options } : options;
    this.deliver = resolved.deliver;
    this.channel = resolved.channel ?? null;
    this.env = resolved.env ?? process.env;
    this.codexWake = resolved.codexWake ?? ((job) => wakeCodex(job));
    this.presenceOf = resolved.presenceOf;
    this.locationOf = resolved.locationOf;
    this.claude = new ClaudeWake((job, result) => store.wakes.finish(job, result));
  }

  start(): void {
    this.heartbeat();
    this.timer = setInterval(() => {
      this.heartbeat();
      void this.flush().catch(() => {});
      if (Date.now() - this.approvalsCheckedAt >= APPROVAL_CHECK_MS) void this.checkApprovals().catch(() => {});
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
      this.store.wakes.finish(job, result);
    }
  }

  /** agent-relay codex-gated-wake D67: held or offline at once, busy after ten minutes; once per message. */
  private noticeUndelivered(job: WakeJob, result: WakeResult, now = Date.now()): WakeResult {
    const why = result.state === "held"
      ? "Codex could not be woken; the message waits"
      : result.state === "pending" && result.reason === "busy"
        ? (now - job.createdAt >= BUSY_NOTIFY_AFTER_MS ? "Codex has been busy for ten minutes" : null)
        : result.state === "pending" ? "Codex is not running; the message waits" : null;
    if (!why) return result;
    // notice-location D188: "busy" is the Codex app answering on its own socket that it holds this thread; in every
    // other case nothing confirms where the Codex side is, so the notice says only "Codex" and has no click action.
    const where: Location = { place: { kind: result.reason === "busy" ? "codex-app" : "codex" } };
    const notified = notifyUndelivered(job.mailboxPath,
      { messageId: job.messageId, fromAgent: job.fromAgent, agent: job.agent, why,
        body: this.store.messageById(job.messageId)?.body, where }, this.env);
    return notified ? { ...result, detail: `${result.detail} ${NOTIFIED_TEXT}` } : result;
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
    const sessions = this.presenceOf ? null : await claudeSessionsOrNull();
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
