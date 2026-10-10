// agent-relay notice-location D188: where a session is, so a desktop notice can say it and a click can go there.
// A click only brings a window forward. Whatever reaches a command line here is a value this bridge verified and
// format-checked (tty, bundle id); names, paths and message text are for display only and never pass through here.
import { execFile } from "node:child_process";
import { basename } from "node:path";
import { promisify } from "node:util";

const execute = promisify(execFile);

export const CLAUDE_DESKTOP = "com.anthropic.claudefordesktop";
export const CODEX_APP = "com.openai.codex";
export const TERMINAL = "com.apple.Terminal";
export const ITERM = "com.googlecode.iterm2";

export type Place =
  | { kind: "desktop" }
  | { kind: "terminal"; tty: string; bundle: string | null; app: string | null }
  | { kind: "background"; id: string }
  | { kind: "codex-app" }
  | { kind: "codex" }
  | { kind: "unknown" };

/** A place plus what may be shown about it: the session's own name and its project folder (display text only). */
export interface Location { place: Place; session?: string; project?: string }

export interface OwningApp { bundle: string | null; name: string | null }

export const validTty = (tty: unknown): string | null =>
  typeof tty === "string" && /^ttys\d{1,4}$/.test(tty) ? tty : null;

export const validBundle = (bundle: unknown): string | null =>
  typeof bundle === "string" && /^[A-Za-z0-9.-]{1,128}$/.test(bundle) ? bundle : null;

/** The outermost `.app` of an absolute executable path (VS Code's "Code Helper.app" lives inside the real app). */
export function outermostApp(path: string): string | null {
  const match = /^(\/.+?\.app)(?:\/|$)/.exec(path);
  return match ? match[1] : null;
}

export function locate(session: { entrypoint?: string; kind?: string; sessionId: string }, tty: string | null,
  owner: OwningApp | null): Place {
  if (session.entrypoint === "claude-desktop") return { kind: "desktop" };
  if (session.kind === "background") {
    const id = /^[0-9a-f]{8}(?=-)/.exec(session.sessionId)?.[0];
    return id ? { kind: "background", id } : { kind: "unknown" };
  }
  const checked = validTty(tty);
  if (session.entrypoint !== "cli" || !checked) return { kind: "unknown" };
  const bundle = validBundle(owner?.bundle);
  return { kind: "terminal", tty: checked, bundle, app: bundle ? owner?.name ?? null : null };
}

export function placeLabel(place: Place): string {
  switch (place.kind) {
    case "desktop": return "Claude desktop app";
    case "terminal": return `${place.app ?? "terminal"} ${place.tty}`;
    case "background": return `background session · claude attach ${place.id}`;
    case "codex-app": return "Codex app";
    case "codex": return "Codex";
    default: return "";
  }
}

/** The place without anything that identifies one session (shown when previews are off). */
export function placeCategory(place: Place): string {
  switch (place.kind) {
    case "terminal": return "terminal";
    case "background": return "background session";
    default: return placeLabel(place);
  }
}

const quoted = (lines: string[]) => lines.map((line) => `-e '${line}'`).join(" ");

/** One fixed command: bring the app forward first (works even when Automation is declined), then select the tab. */
function selectTab(bundle: typeof TERMINAL | typeof ITERM, tty: string): string {
  const script = bundle === TERMINAL
    ? ['tell application "Terminal"', "repeat with w in windows", "repeat with t in tabs of w",
      `if tty of t is "/dev/${tty}" then`, "set selected of t to true", "set index of w to 1", "return", "end if",
      "end repeat", "end repeat", "end tell"]
    : ['tell application "iTerm2"', "repeat with w in windows", "repeat with t in tabs of w",
      "repeat with s in sessions of t", `if tty of s is "/dev/${tty}" then`, "select w", "select t", "select s",
      "return", "end if", "end repeat", "end repeat", "end repeat", "end tell"];
  return `/usr/bin/open -b ${bundle}; /usr/bin/osascript ${quoted(script)}`;
}

/** terminal-notifier arguments for a click on this place; empty when a click has nowhere verified to go. */
export function clickArgs(place: Place): string[] {
  if (place.kind === "desktop") return ["-activate", CLAUDE_DESKTOP];
  if (place.kind === "codex-app") return ["-activate", CODEX_APP];
  if (place.kind !== "terminal") return [];
  const tty = validTty(place.tty);
  const bundle = validBundle(place.bundle);
  if (!tty || !bundle) return [];
  if (bundle === TERMINAL || bundle === ITERM) return ["-execute", selectTab(bundle, tty)];
  return ["-activate", bundle];
}

async function ps(pid: number, columns: string): Promise<string | null> {
  try {
    const { stdout } = await execute("/bin/ps", ["-o", columns, "-p", String(pid)],
      { timeout: 2000, env: { ...process.env, LC_ALL: "C" } });
    return stdout.trim() || null;
  } catch { return null; }
}

/** The app that owns this process's terminal: the outermost `.app` of the first ancestor that runs inside one. */
async function owningApp(pid: number): Promise<OwningApp | null> {
  let current = pid;
  for (let depth = 0; depth < 12; depth += 1) {
    const parent = Number((await ps(current, "ppid=")) ?? NaN);
    if (!Number.isSafeInteger(parent) || parent <= 1) return null;
    const app = outermostApp((await ps(parent, "comm=")) ?? "");
    if (app) {
      try {
        const { stdout } = await execute("/usr/bin/defaults", ["read", `${app}/Contents/Info`, "CFBundleIdentifier"],
          { timeout: 2000 });
        return { bundle: validBundle(stdout.trim()), name: basename(app, ".app") };
      } catch { return { bundle: null, name: null }; }
    }
    current = parent;
  }
  return null;
}

/** Where a live Claude session is. `session` must come from the registry reader, which checked pid and start time. */
export async function claudeLocation(session: { pid: number; sessionId: string; name?: string; cwd?: string;
  entrypoint?: string; kind?: string }): Promise<Location> {
  const shown = { session: session.name || undefined, project: session.cwd ? basename(session.cwd) : undefined };
  if (process.platform !== "darwin") return { place: { kind: "unknown" }, ...shown };
  const early = locate(session, null, null);
  if (early.kind !== "unknown" || session.entrypoint !== "cli") return { place: early, ...shown };
  const tty = validTty(await ps(session.pid, "tty="));
  return { place: locate(session, tty, tty ? await owningApp(session.pid) : null), ...shown };
}
