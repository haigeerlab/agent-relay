// agent-relay presence-and-approval D146: is a mailbox agent's host session running, stopped or waiting for the user?
// Read only: Claude Code's own session registry and the Codex app's thread-owner reply. Nothing is started or answered.
import { homedir } from "node:os";
import { join } from "node:path";
import type { ClaudeSession } from "./claude-wake.js";
import { CODEX_NOT_LOADED, silentAboutTask } from "./codex-wake.js";
import { CodexIpc } from "./local-ipc.js";

/** codex-not-loaded D200: `not-loaded` is a Codex task the app does not answer for. A consumer treats a value it does not
 * know as `unknown` (more may be added within interface 2.x). */
export type PresenceState = "running" | "waiting-approval" | "waiting-input" | "stopped" | "not-loaded" | "unknown";

export interface Presence {
  state: PresenceState;
  /** When Claude Code last changed the session's status (ISO time), if it says. */
  since?: string;
  /** What the session waits for, in Claude Code's words. */
  detail?: string;
  /** agents-view-polish D225: for a running Claude session, whether it is in a turn (`busy`) or between turns (`idle`). */
  activity?: "busy" | "idle";
}

/** `sessions` are the live Claude sessions (claudeSessions()), or null where they cannot be read. */
export function claudePresence(sessionId: string, sessions: ClaudeSession[] | null): Presence {
  if (sessions === null) return { state: "unknown", detail: "Claude sessions cannot be read here" };
  const found = sessions.find((s) => s.sessionId === sessionId || s.bridgeSessionId === sessionId);
  if (!found) return { state: "stopped" };
  const since = found.statusUpdatedAt === undefined ? {} : { since: new Date(found.statusUpdatedAt).toISOString() };
  const activity = found.status === "busy" || found.status === "idle" ? { activity: found.status as "busy" | "idle" } : {};
  if (found.status !== "waiting") return { state: "running", ...since, ...activity };
  const detail = found.waitingFor ? { detail: found.waitingFor } : {};
  return { state: /permission/i.test(found.waitingFor ?? "") ? "waiting-approval" : "waiting-input", ...since, ...detail };
}

/** Does the Codex app hold this thread? true: an owner is connected; false: none; null: the app cannot be asked. */
export async function codexOwner(threadId: string, path = join(homedir(), ".codex", "ipc", "ipc.sock"),
  options: { responseTimeoutMs?: number } = {}): Promise<boolean | "not-loaded" | null> {
  if (process.platform === "win32") return null;
  const ipc = new CodexIpc(options);
  let connected = false;
  try {
    await ipc.connect(path);
    connected = true;
    const owner = await ipc.request("thread-owner-discovery", { hostId: "local", conversationId: threadId }, 1);
    return owner.resultType === "success" && !!owner.handledByClientId;
  } catch (error) {
    return silentAboutTask(error, connected) ? "not-loaded" : null;
  } finally { ipc.close(); }
}

export function codexPresence(owner: boolean | "not-loaded" | null): Presence {
  return owner === null ? { state: "unknown", detail: "the Codex app cannot be asked" }
    : owner === "not-loaded" ? { state: "not-loaded", detail: CODEX_NOT_LOADED }
      : { state: owner ? "running" : "stopped" };
}
