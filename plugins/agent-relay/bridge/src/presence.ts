// agent-relay presence-and-approval D146: is a mailbox agent's host session running, stopped or waiting for the user?
// Read only: Claude Code's own session registry and the Codex app's thread-owner reply. Nothing is started or answered.
import { homedir } from "node:os";
import { join } from "node:path";
import type { ClaudeSession } from "./claude-wake.js";
import { CODEX_NOT_LOADED, silentAboutTask } from "./codex-wake.js";
import { CodexIpc, IPC_RESPONSE_TIMEOUT_MS } from "./local-ipc.js";

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

/** codex-approval-presence D233: a pending request the ChatGPT app shows the user, by its `method`. */
const CODEX_WAITING: Record<string, { state: "waiting-approval" | "waiting-input"; detail: string }> = {
  "item/commandExecution/requestApproval":
    { state: "waiting-approval", detail: "waiting for your approval to run a command in its Codex task" },
  "item/fileChange/requestApproval":
    { state: "waiting-approval", detail: "waiting for your approval to change files in its Codex task" },
  "item/permissions/requestApproval":
    { state: "waiting-approval", detail: "waiting for your approval of a permission request in its Codex task" },
  "item/tool/requestUserInput": { state: "waiting-input", detail: "waiting for your answer in its Codex task" },
  "mcpServer/elicitation/request":
    { state: "waiting-input", detail: "waiting for your answer to a tool's question in its Codex task" },
};

/**
 * codex-approval-presence D233, D234: the waiting state in a follower snapshot's `conversationState`, or null. Reads
 * only each request's `method`, `completed` and `params.startedAtMs`; nothing else of the conversation is looked at.
 * Approval wins over input; `since` is the earliest start among the requests of that kind.
 */
export function codexWaiting(conversationState: unknown): Presence | null {
  const requests = (conversationState as { requests?: unknown } | null)?.requests;
  if (!Array.isArray(requests)) return null;
  let found: { state: "waiting-approval" | "waiting-input"; detail: string; startedAt?: number } | null = null;
  for (const entry of requests) {
    if (!entry || typeof entry !== "object") continue;
    const { method, completed } = entry as { method?: unknown; completed?: unknown };
    const kind = typeof method === "string" && completed !== true ? CODEX_WAITING[method] : undefined;
    if (!kind || (found?.state === "waiting-approval" && kind.state === "waiting-input")) continue;
    const started = (entry as { params?: { startedAtMs?: unknown } }).params?.startedAtMs;
    const startedAt = typeof started === "number" && Number.isFinite(started) && started > 0 ? started : undefined;
    if (!found || found.state !== kind.state) found = { ...kind, startedAt };
    else if (startedAt !== undefined && (found.startedAt === undefined || startedAt < found.startedAt)) found.startedAt = startedAt;
  }
  if (!found) return null;
  return { state: found.state, ...(found.startedAt === undefined ? {} : { since: new Date(found.startedAt).toISOString() }),
    detail: found.detail };
}

const FOLLOW = "thread-stream-following-changed";

/**
 * codex-approval-presence D232, D235: a Codex task's presence, with its waiting state when the app has it loaded.
 * Discovery as `codexOwner`; only with an owner, one follow broadcast to that owner, the first follower change read
 * within what is left of `responseTimeoutMs`, then an unfollow. Anything unexpected keeps the owner's answer, `running`.
 */
export async function codexTaskPresence(threadId: string, path = join(homedir(), ".codex", "ipc", "ipc.sock"),
  options: { responseTimeoutMs?: number } = {}): Promise<Presence> {
  if (process.platform === "win32") return codexPresence(null);
  const started = Date.now();
  const cap = options.responseTimeoutMs ?? IPC_RESPONSE_TIMEOUT_MS;
  const ipc = new CodexIpc(options);
  let connected = false;
  let owner: unknown;
  try {
    await ipc.connect(path);
    connected = true;
    const found = await ipc.request("thread-owner-discovery", { hostId: "local", conversationId: threadId }, 1);
    owner = found.resultType === "success" ? found.handledByClientId : undefined;
  } catch (error) {
    ipc.close();
    return codexPresence(silentAboutTask(error, connected) ? "not-loaded" : null);
  }
  if (!owner || typeof owner !== "string") {
    ipc.close();
    return codexPresence(!!owner);
  }
  const follow = (following: boolean) =>
    ipc.broadcast(FOLLOW, { conversationId: threadId, hostId: "local", following }, [owner as string]);
  try {
    const change = ipc.nextChange(threadId, Math.max(0, cap - (Date.now() - started)));
    follow(true);
    const got = await change;
    return (got.type === "snapshot" ? codexWaiting(got.conversationState) : null) ?? { state: "running" };
  } catch {
    return { state: "running" };
  } finally {
    follow(false);
    ipc.close(true);
  }
}

export function codexPresence(owner: boolean | "not-loaded" | null): Presence {
  return owner === null ? { state: "unknown", detail: "the Codex app cannot be asked" }
    : owner === "not-loaded" ? { state: "not-loaded", detail: CODEX_NOT_LOADED }
      : { state: owner ? "running" : "stopped" };
}
