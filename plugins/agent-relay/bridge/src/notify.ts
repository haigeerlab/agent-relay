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
  /** Deduplication key; defaults to the message id. A distinct event about the same message passes its own key. */
  key?: string;
  /** The message text, for the preview (notify-channel D89). */
  body?: string;
  /** A notice about an event rather than a waiting message. */
  event?: "gate-off";
}

// agent-relay notify-channel D89 (reverses codex-gated-wake D67's "never the body", confirmed by the user 2026-10-08):
// a notice says what the work is. `notify-preview.off` next to the mailbox restores the D67 form.
export const PREVIEW_CHARS = 60;
export const NAME_CHARS = 40;
/** notify-channel D89a: the reason stays in the subtitle (it may ask the user to act). */
export const REASON_CHARS = 80;
export const PREVIEW_OFF_FILE = "notify-preview.off";

/** One line: control characters (C0, DEL, C1, U+2028/2029) become spaces, runs collapse, cut at `max` code points. */
export function oneLine(text: string, max: number): string {
  const flat = text.replace(/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/g, " ").replace(/\s+/g, " ").trim();
  const chars = Array.from(flat);
  return chars.length > max ? chars.slice(0, max).join("").trimEnd() + "…" : flat;
}

export interface NoticeFields {
  title: string;
  subtitle: string;
  body: string;
}

/** What the desktop notice shows. Title and subtitle always start with a fixed prefix, never with a dash. */
export function noticeFields(notice: UndeliveredNotice, { preview }: { preview: boolean }): NoticeFields {
  if (!preview) return { title: "agent-relay", subtitle: "", body: noticeText(notice) };
  const subtitle = `#${notice.messageId} · ${oneLine(notice.agent, NAME_CHARS)}`;
  if (notice.event === "gate-off" || notice.body === undefined) {
    return { title: notice.event === "gate-off" ? "agent-relay · gated Codex wake off" : "agent-relay", subtitle,
      body: noticeText(notice) };
  }
  return {
    title: `agent-relay · ${oneLine(notice.fromAgent ?? "a peer", NAME_CHARS) || "a peer"} → Codex`,
    subtitle: `${subtitle} · ${oneLine(notice.why, REASON_CHARS)}`,
    body: oneLine(notice.body, PREVIEW_CHARS) || "(empty message)",
  };
}

// agent-relay acceptance-030-gaps D76: osascript returns 0 even when macOS drops the banner, so say only that it was tried.
export const NOTIFIED_TEXT = "A desktop notification was attempted on this Mac; macOS may not show it " +
  "(Script Editor notifications off, or Focus). The user can list waiting messages with doctor or by asking any session.";

export function noticeText(notice: UndeliveredNotice): string {
  return `${JSON.stringify(notice.fromAgent ?? "a peer")} gave Codex work: message #${notice.messageId} to ` +
    `${JSON.stringify(notice.agent)} (${notice.why}).`;
}

/**
 * Show one desktop notification for this message unless it was already shown by any bridge on this mailbox.
 * Off with `AGENT_RELAY_NOTIFY=off` or a `notify.off` file next to the mailbox; `AGENT_RELAY_NOTIFY_LOG` records the
 * fields in a file instead of showing them (tests). Shows a short preview of the message (D89) unless
 * `notify-preview.off` is next to the mailbox. Returns true when this call notified.
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
    writeFileSync(join(marks, notice.key ?? String(notice.messageId)), "", { flag: "wx", mode: 0o600 });
  } catch {
    return false; // already notified (another bridge won the race), or the mark cannot be kept: never notify twice
  }
  const fields = noticeFields(notice, { preview: !existsSync(join(dir, PREVIEW_OFF_FILE)) });
  if (log) {
    appendFileSync(log, `${fields.title} | ${fields.subtitle} | ${fields.body}\n`);
    return true;
  }
  // The texts are arguments, never part of the script.
  execFile("osascript", ["-e", "on run argv", "-e",
    "display notification (item 3 of argv) with title (item 1 of argv) subtitle (item 2 of argv)", "-e", "end run",
    fields.title, fields.subtitle, fields.body], () => {});
  return true;
}
