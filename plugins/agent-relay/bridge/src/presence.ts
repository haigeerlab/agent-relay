// agent-relay presence-and-approval D146: is a mailbox agent's host session running, stopped or waiting for the user?
// Read only: Claude Code's own session registry and the Codex app's thread-owner reply. Nothing is started or answered.
import { homedir } from "node:os";
import { join } from "node:path";
import type { ClaudeSession } from "./claude-wake.js";
import { CodexIpc } from "./local-ipc.js";

export type PresenceState = "running" | "waiting-approval" | "waiting-input" | "stopped" | "unknown";

export interface Presence {
  state: PresenceState;
  /** When Claude Code last changed the session's status (ISO time), if it says. */
  since?: string;
  /** What the session waits for, in Claude Code's words. */
  detail?: string;
}

/** `sessions` are the live Claude sessions (claudeSessions()), or null where they cannot be read. */
export function claudePresence(sessionId: string, sessions: ClaudeSession[] | null): Presence {
  if (sessions === null) return { state: "unknown", detail: "Claude sessions cannot be read here" };
  const found = sessions.find((s) => s.sessionId === sessionId || s.bridgeSessionId === sessionId);
  if (!found) return { state: "stopped" };
  const since = found.statusUpdatedAt === undefined ? {} : { since: new Date(found.statusUpdatedAt).toISOString() };
  if (found.status !== "waiting") return { state: "running", ...since };
  const detail = found.waitingFor ? { detail: found.waitingFor } : {};
  return { state: /permission/i.test(found.waitingFor ?? "") ? "waiting-approval" : "waiting-input", ...since, ...detail };
}

/** Does the Codex app hold this thread? true: an owner is connected; false: none; null: the app cannot be asked. */
export async function codexOwner(threadId: string,
  path = join(homedir(), ".codex", "ipc", "ipc.sock")): Promise<boolean | null> {
  if (process.platform === "win32") return null;
  const ipc = new CodexIpc();
  try {
    await ipc.connect(path);
    const owner = await ipc.request("thread-owner-discovery", { hostId: "local", conversationId: threadId }, 1);
    return owner.resultType === "success" && !!owner.handledByClientId;
  } catch {
    return null;
  } finally { ipc.close(); }
}

export function codexPresence(owner: boolean | null): Presence {
  return owner === null ? { state: "unknown", detail: "the Codex app cannot be asked" }
    : { state: owner ? "running" : "stopped" };
}
