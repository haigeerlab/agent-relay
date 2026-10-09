// agent-relay codex-gated-wake D67: tell the user on this Mac when a Codex message cannot be delivered, once per message.
import { execFile } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, writeFileSync } from "node:fs";
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
  /** presence-and-approval D148: a Claude session waiting for the user's approval, not undelivered Codex work. */
  kind?: "approval";
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
  if (notice.kind === "approval") {
    const agent = oneLine(notice.agent, NAME_CHARS);
    return { title: preview ? `agent-relay · ${agent} waits for you` : "agent-relay",
      subtitle: preview ? `#${notice.messageId} · ${agent}` : "", body: noticeText(notice) };
  }
  if (!preview) return { title: "agent-relay", subtitle: "", body: noticeText(notice) };
  const subtitle = `#${notice.messageId} · ${oneLine(notice.agent, NAME_CHARS)}`;
  if (notice.body === undefined) return { title: "agent-relay", subtitle, body: noticeText(notice) };
  return {
    title: `agent-relay · ${oneLine(notice.fromAgent ?? "a peer", NAME_CHARS) || "a peer"} → Codex`,
    subtitle: `${subtitle} · ${oneLine(notice.why, REASON_CHARS)}`,
    body: oneLine(notice.body, PREVIEW_CHARS) || "(empty message)",
  };
}

// agent-relay acceptance-030-gaps D76: osascript returns 0 even when macOS drops the banner, so say only that it was tried.
export const NOTIFIED_TEXT = "A desktop notification was attempted on this Mac; macOS may not show it " +
  "(notifications not allowed for the app that shows them, or Focus). The user can list waiting messages with doctor or by asking any session.";

export function noticeText(notice: UndeliveredNotice): string {
  if (notice.kind === "approval") {
    return `${oneLine(notice.agent, NAME_CHARS)} is ${notice.why}; message #${notice.messageId} from ` +
      `${JSON.stringify(notice.fromAgent ?? "a peer")} waits until you answer it there.`;
  }
  return `${JSON.stringify(notice.fromAgent ?? "a peer")} gave Codex work: message #${notice.messageId} to ` +
    `${JSON.stringify(notice.agent)} (${notice.why}).`;
}

// agent-relay notify-channel D83: Homebrew's terminal-notifier (Apple silicon, then Intel prefix), never found via PATH.
export const NOTIFIER_CANDIDATES = ["/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier"];

/**
 * The first candidate that resolves to a regular, executable file owned by this user or root and not writable by group
 * or others; the resolved path is what runs. Null when none qualifies.
 */
export function findNotifier(candidates: readonly string[] = NOTIFIER_CANDIDATES): string | null {
  const uid = process.getuid?.();
  for (const candidate of candidates) {
    try {
      const real = realpathSync(candidate);
      const info = statSync(real);
      if (!info.isFile() || (info.mode & 0o111) === 0 || (info.mode & 0o022) !== 0) continue;
      if (info.uid !== 0 && info.uid !== uid) continue;
      return real;
    } catch { /* missing or unreadable: next */ }
  }
  return null;
}

export interface NoticeChannel {
  candidates?: readonly string[];
  osascript?: string;
}

/**
 * agent-relay presence-polish D175: when a waiting episode carries no start time of its own, the first bridge to see it
 * records one next to the notice marks, so every bridge on the mailbox keys the episode alike; seeing the session not
 * waiting ends the episode. Returns the episode start while waiting, null otherwise or when it cannot be kept.
 */
export function waitingEpisode(mailboxPath: string, sessionId: string, waiting: boolean,
  now: () => number = Date.now): string | null {
  if (!isAbsolute(mailboxPath)) return null;
  const marks = join(dirname(mailboxPath), "notified");
  const file = join(marks, episodeFile(sessionId));
  try {
    if (!waiting) {
      rmSync(file, { force: true });
      return null;
    }
    mkdirSync(marks, { recursive: true, mode: 0o700 });
    try {
      writeFileSync(file, String(now()), { flag: "wx", mode: 0o600 });
    } catch { /* another bridge (or an earlier check) started this episode */ }
    const start = readFileSync(file, "utf8").trim();
    return /^\d+$/.test(start) ? start : null;
  } catch {
    return null;
  }
}

const episodeFile = (sessionId: string) => `episode-${sessionId.replace(/[^A-Za-z0-9._-]/g, "_")}`;

/**
 * agent-relay install-docs-accuracy D180: a session whose message was handled leaves the waiting list, so nothing sees
 * its episode end; remove the episode marks of every session not in `waiting` (the sessions that still have one).
 * Marks younger than ten minutes stay: another bridge may have just started one for a message this list missed.
 */
export function pruneWaitingEpisodes(mailboxPath: string, waiting: Iterable<string>, now = Date.now()): void {
  if (!isAbsolute(mailboxPath)) return;
  const marks = join(dirname(mailboxPath), "notified");
  const keep = new Set([...waiting].map(episodeFile));
  let names: string[];
  try { names = readdirSync(marks); } catch { return; }
  for (const name of names) {
    if (!name.startsWith("episode-") || keep.has(name)) continue;
    try {
      if (now - statSync(join(marks, name)).mtimeMs >= 10 * 60_000) rmSync(join(marks, name), { force: true });
    } catch { /* removed meanwhile */ }
  }
}

/** The notice key as a file and group name: only `[A-Za-z0-9._-]`. */
function safeKey(notice: UndeliveredNotice): string {
  return (notice.key ?? String(notice.messageId)).replace(/[^A-Za-z0-9._-]/g, "_");
}

/**
 * Show one desktop notification for this message unless it was already shown by any bridge on this mailbox.
 * Off with `AGENT_RELAY_NOTIFY=off` or a `notify.off` file next to the mailbox; `AGENT_RELAY_NOTIFY_LOG` records the
 * fields in a file instead of showing them (tests). Shows a short preview of the message (D89) unless
 * `notify-preview.off` is next to the mailbox. Returns true when this call notified.
 */
export function notifyUndelivered(mailboxPath: string, notice: UndeliveredNotice,
  env: NodeJS.ProcessEnv = process.env, channel: NoticeChannel = {}): boolean {
  if (env.AGENT_RELAY_NOTIFY === "off" || !isAbsolute(mailboxPath)) return false;
  const dir = dirname(mailboxPath);
  if (existsSync(join(dir, "notify.off"))) return false;
  const log = env.AGENT_RELAY_NOTIFY_LOG;
  if (!log && process.platform !== "darwin") return false;
  try {
    const marks = join(dir, "notified");
    mkdirSync(marks, { recursive: true, mode: 0o700 });
    writeFileSync(join(marks, safeKey(notice)), "", { flag: "wx", mode: 0o600 });
  } catch {
    return false; // already notified (another bridge won the race), or the mark cannot be kept: never notify twice
  }
  const fields = noticeFields(notice, { preview: !existsSync(join(dir, PREVIEW_OFF_FILE)) });
  if (log) {
    appendFileSync(log, `${fields.title} | ${fields.subtitle} | ${fields.body}\n`);
    return true;
  }
  // notify-channel D84/D86: the preview goes on stdin, never as an argument; one group per notice. A failure is not
  // retried through osascript, which could show the same notice twice.
  const notifier = findNotifier(channel.candidates);
  if (notifier) {
    const child = execFile(notifier, ["-title", fields.title, "-subtitle", fields.subtitle, "-group", `agent-relay-${safeKey(notice)}`],
      { timeout: 10_000 }, () => {});
    child.stdin?.on("error", () => {});
    child.stdin?.end(fields.body);
    return true;
  }
  // The texts are arguments, never part of the script.
  const fallback = execFile(channel.osascript ?? "osascript", ["-e", "on run argv", "-e",
    "display notification (item 3 of argv) with title (item 1 of argv) subtitle (item 2 of argv)", "-e", "end run",
    fields.title, fields.subtitle, fields.body], { timeout: 10_000 }, () => {});
  fallback.stdin?.on("error", () => {});
  fallback.stdin?.end();
  return true;
}
