import type { BridgeStore } from "./bridge-store.js";
import { channelNotification, type ChannelNotification } from "./claude-channel.js";
import { ClaudeWake } from "./claude-wake.js";
import { existsSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join } from "node:path";
import { type CodexGate, defaultCodexGate, GATE_OFF_FILE, gateUnverified, type VerifyOptions, verifyTurn } from "./codex-gate.js";
import { wakeCodex } from "./codex-wake.js";
import { BUSY_NOTIFY_AFTER_MS, NOTIFIED_TEXT, notifyUndelivered } from "./notify.js";
import type { WakeJob, WakeResult } from "./wake-queue.js";

/** Push path into the Claude session hosting this MCP process (opt-in). */
export interface ChannelDelivery {
  sessionId: string;
  send(notification: ChannelNotification): Promise<void>;
}

export interface DispatcherOptions {
  deliver?: (job: WakeJob) => Promise<WakeResult>;
  channel?: ChannelDelivery | null;
  /** Environment for notifications and the Codex gate (CODEX_HOME); defaults to this process's. */
  env?: NodeJS.ProcessEnv;
  /** agent-relay codex-gated-wake D66: injectable for tests. */
  codexWake?: (job: WakeJob, ready: () => string | null) => Promise<WakeResult>;
  gate?: CodexGate;
  verify?: VerifyOptions;
}

export class WakeDispatcher {
  private running: Promise<void> | null = null;
  private stopped = false;
  private timer: NodeJS.Timeout | null = null;
  private claude: ClaudeWake;
  private deliver?: (job: WakeJob) => Promise<WakeResult>;
  private channel: ChannelDelivery | null;
  private env: NodeJS.ProcessEnv;
  private codexWake: (job: WakeJob, ready: () => string | null) => Promise<WakeResult>;
  private gate: CodexGate;
  private verify: VerifyOptions;

  constructor(private store: BridgeStore, options: DispatcherOptions | ((job: WakeJob) => Promise<WakeResult>) = {}) {
    const resolved = typeof options === "function" ? { deliver: options } : options;
    this.deliver = resolved.deliver;
    this.channel = resolved.channel ?? null;
    this.env = resolved.env ?? process.env;
    this.codexWake = resolved.codexWake ?? ((job, ready) => wakeCodex(job, ready));
    this.gate = resolved.gate ?? defaultCodexGate(this.env);
    this.verify = resolved.verify ?? {};
    this.claude = new ClaudeWake((job, result) => store.wakes.finish(job, result));
  }

  start(): void {
    this.heartbeat();
    this.timer = setInterval(() => {
      this.heartbeat();
      void this.flush().catch(() => {});
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
      ? (result.detail.startsWith("Gated Codex wake is turned off")
        ? "gated Codex wake is off; check Codex, then delete codex-gate.off next to the mailbox"
        : "Codex could not be woken safely; the message waits")
      : result.state === "pending" && result.reason === "busy"
        ? (now - job.createdAt >= BUSY_NOTIFY_AFTER_MS ? "Codex has been busy for ten minutes" : null)
        : result.state === "pending" ? "Codex is not running; the message waits" : null;
    if (!why) return result;
    const notified = notifyUndelivered(job.mailboxPath,
      { messageId: job.messageId, fromAgent: job.fromAgent, agent: job.agent, why,
        body: this.store.messageById(job.messageId)?.body }, this.env);
    return notified ? { ...result, detail: `${result.detail} ${NOTIFIED_TEXT}` } : result;
  }

  /**
   * agent-relay codex-gated-wake D66 (replaces identity-check D38's hold): every Codex wake carries the approval gate
   * (D65). It is sent only when the ChatGPT app is new enough (the real barrier for old apps); afterwards the woken
   * turn's own record must show the gate (a backstop), else gated wake turns off for this mailbox and the user is told.
   */
  private async gatedCodexWake(job: WakeJob): Promise<WakeResult> {
    const dir = isAbsolute(job.mailboxPath) ? dirname(job.mailboxPath) : null;
    const off = dir ? join(dir, GATE_OFF_FILE) : null;
    if (off && existsSync(off)) {
      return { state: "held", detail: `Gated Codex wake is turned off for this mailbox (${off}): an earlier woken ` +
        "turn did not show the approval gate. Delete that file after checking Codex to turn it back on." };
    }
    const result = await this.codexWake(job, () => gateUnverified(this.gate));
    if (result.state !== "accepted" || !result.turnId) return result;
    const verdict = await verifyTurn(this.gate, job.target.sessionId, result.turnId, this.verify);
    if (verdict === "ok") return result;
    if (off) {
      try { writeFileSync(off, `turn ${result.turnId} of ${job.target.sessionId}: ${verdict}\n`, { mode: 0o600 }); } catch { /* still told */ }
    }
    const notified = notifyUndelivered(job.mailboxPath, { messageId: job.messageId, fromAgent: job.fromAgent, agent: job.agent,
      why: `the woken turn did not show the approval gate (${verdict}); gated Codex wake is off until you check Codex`,
      key: `gate-${result.turnId}`, event: "gate-off" }, this.env);
    return { ...result, detail: `${result.detail}. Its record did not show the approval gate (${verdict}); gated Codex ` +
      `wake is now off for this mailbox.${notified ? ` ${NOTIFIED_TEXT}` : ""}` };
  }

  private async dispatch(job: WakeJob): Promise<WakeResult> {
    if (this.deliver) return this.deliver(job);
    if (this.channel && job.target.app === "claude" && job.target.sessionId === this.channel.sessionId) {
      await this.channel.send(channelNotification(job));
      // Claude Code sends no receipt for channel events; an inbox read marks it read.
      return { state: "unknown", detail: "Pushed to this Claude Code session's channel; Claude Code returns no receipt. No automatic replay." };
    }
    if (job.target.app === "codex") return this.gatedCodexWake(job);
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
