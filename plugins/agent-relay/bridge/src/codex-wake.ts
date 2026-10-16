import { homedir } from "node:os";
import { join } from "node:path";
import { CodexIpc, IpcError } from "./local-ipc.js";
import { wakeNotice, type WakeJob, type WakeResult } from "./wake-queue.js";

export function codexTurn(job: WakeJob) {
  const text = wakeNotice(job);
  const callId = "bridge_" + job.attemptId;
  // Peer content is a tool result, never a system/developer/user instruction.
  return {
    conversationId: job.target.sessionId,
    turnStart: {
      // agent-relay wake-any-mode D140 (supersedes codex-gated-wake D65): the woken turn runs under the task's own
      // approval and sandbox settings; the bridge sets neither.
      request: { threadId: job.target.sessionId, input: [] },
      context: {
        responseItems: [
          { type: "function_call", call_id: callId, name: "untrusted_input", arguments: "{}" },
          { type: "function_call_output", call_id: callId,
            output: [{ type: "input_text", text }] },
        ],
      },
    },
  };
}

/**
 * agent-relay codex-not-loaded D200: the app took the connection but did not answer about this task. Usually the task
 * was not opened since the app started; a deleted task or a wrong id looks the same, so the words do not claim more.
 */
export const CODEX_NOT_LOADED = "The ChatGPT app did not answer for this Codex task, usually because it was not opened " +
  "since the app started; open it and the message is delivered. If the task can no longer be found, it may have been " +
  "deleted: join the mailbox again from a new task.";

/** Was this the app staying silent about one task (connected and initialized, then no answer in time)? */
export function silentAboutTask(error: unknown, connected: boolean): boolean {
  return connected && error instanceof IpcError && error.timedOut;
}

export async function wakeCodex(job: WakeJob, path = join(homedir(), ".codex", "ipc", "ipc.sock"),
  options: { responseTimeoutMs?: number } = {}): Promise<WakeResult> {
  if (process.platform === "win32") return { state: "refused", detail: "Native desktop wake adapter requires Unix local sockets" };
  const ipc = new CodexIpc(options);
  let submitted = false;
  let connected = false;
  try {
    await ipc.connect(path);
    connected = true;
    const owner = await ipc.request("thread-owner-discovery",
      { hostId: "local", conversationId: job.target.sessionId }, 1);
    if (owner.resultType !== "success" || !owner.handledByClientId) {
      return { state: "pending", detail: "Codex task has no connected owner", reason: "offline" };
    }
    if (owner.result?.supportsUntrustedAppInput !== true) {
      return { state: "refused", detail: "Codex owner does not support peer content; update the app" };
    }
    submitted = true;
    const reply = await ipc.request("thread-follower-start-turn", codexTurn(job), 2, owner.handledByClientId);
    if (reply.resultType === "success") {
      if (typeof reply.result?.result?.turn?.id !== "string") {
        return { state: "unknown", detail: "Codex returned an unfamiliar receipt; check the task before retrying" };
      }
      return { state: "accepted", detail: "Codex confirmed a new turn" };
    }
    // This exact native guard runs before context injection or turn creation.
    if (reply.error === "App context must wait until the current turn finishes") {
      return { state: "pending", detail: "Codex is working; ping will wait for idle", reason: "busy" };
    }
    return { state: "unknown", detail: "Codex did not confirm the turn; check the task before retrying" };
  } catch (error) {
    if (submitted) return { state: "unknown", detail: "Codex delivery outcome unavailable; no automatic replay" };
    return silentAboutTask(error, connected)
      ? { state: "pending", detail: CODEX_NOT_LOADED, reason: "offline" }
      : { state: "pending", detail: "Codex local connection unavailable", reason: "offline" };
  } finally { ipc.close(); }
}
