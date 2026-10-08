// agent-relay codex-gated-wake D67: tell the user on this Mac when a Codex message cannot be delivered, once per message.
import { execFile } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join } from "node:path";

/** A Codex recipient that is merely busy is notified only after this long (the user's choice, 2026-10-08). */
export const BUSY_NOTIFY_AFTER_MS = 10 * 60_000;

export interface UndeliveredNotice {
  messageId: number;
  fromAgent?: string;
  agent: string;
  why: string;
}

export const NOTIFIED_TEXT = "The user was notified on this Mac.";

export function noticeText(notice: UndeliveredNotice): string {
  return `${JSON.stringify(notice.fromAgent ?? "a peer")} gave Codex work: message #${notice.messageId} to ` +
    `${JSON.stringify(notice.agent)} (${notice.why}).`;
}

/**
 * Show one desktop notification for this message unless it was already shown by any bridge on this mailbox.
 * Off with `AGENT_RELAY_NOTIFY=off` or a `notify.off` file next to the mailbox; `AGENT_RELAY_NOTIFY_LOG` records the
 * text in a file instead of showing it (tests). Never the message body. Returns true when this call notified.
 */
export function notifyUndelivered(mailboxPath: string, notice: UndeliveredNotice,
  env: NodeJS.ProcessEnv = process.env): boolean {
  if (env.AGENT_RELAY_NOTIFY === "off" || !isAbsolute(mailboxPath)) return false;
  const dir = dirname(mailboxPath);
  if (existsSync(join(dir, "notify.off"))) return false;
  const log = env.AGENT_RELAY_NOTIFY_LOG;
  if (!log && process.platform !== "darwin") return false;
  try {
    const marks = join(dir, "notified");
    mkdirSync(marks, { recursive: true, mode: 0o700 });
    writeFileSync(join(marks, String(notice.messageId)), "", { flag: "wx", mode: 0o600 });
  } catch {
    return false; // already notified (another bridge won the race), or the mark cannot be kept: never notify twice
  }
  const text = noticeText(notice);
  if (log) {
    appendFileSync(log, text + "\n");
    return true;
  }
  // The text is an argument, never part of the script.
  execFile("osascript", ["-e", "on run argv", "-e", 'display notification (item 1 of argv) with title "agent-relay"',
    "-e", "end run", text], () => {});
  return true;
}
