// agent-relay awaiting-reply-view D203: the recipients' presence for the open requests on one outbox page, capped in
// cost. Claude presence is a registry read; a Codex lookup asks the ChatGPT app and waits at most 2 s here (a loaded task
// answers in milliseconds), so one silent task cannot hold the call near the 10 s IPC timeout.
import { codexOwner, codexPresence, type Presence } from "./presence.js";
import type { WakeTarget } from "./wake-queue.js";

export const AWAITING_PRESENCE_TIMEOUT_MS = 2000;
export const CODEX_NO_ANSWER_SHORT =
  "the ChatGPT app did not answer within 2 s; usually the task was not opened since the app started";

/** A Codex recipient's presence for the awaiting view; a silence is reported as unknown, not as not-loaded. */
export async function awaitingCodexPresence(threadId: string, path?: string): Promise<Presence> {
  const owner = await codexOwner(threadId, path, { responseTimeoutMs: AWAITING_PRESENCE_TIMEOUT_MS });
  return owner === "not-loaded" ? { state: "unknown", detail: CODEX_NO_ANSWER_SHORT } : codexPresence(owner);
}

/**
 * Presence per distinct recipient, looked up in parallel. A retired recipient gets none and a recipient with no
 * recorded host session gets "unknown" without a lookup.
 */
export async function pagePresence(
  recipients: string[],
  hostOf: (name: string) => { host: WakeTarget | null; retired: boolean } | undefined,
  lookup: (host: WakeTarget) => Promise<Presence>,
): Promise<Map<string, Presence>> {
  const result = new Map<string, Presence>();
  await Promise.all([...new Set(recipients)].map(async (name) => {
    const recipient = hostOf(name);
    if (recipient?.retired) return;
    result.set(name, recipient?.host ? await lookup(recipient.host)
      : { state: "unknown", detail: "no recorded host session" });
  }));
  return result;
}
