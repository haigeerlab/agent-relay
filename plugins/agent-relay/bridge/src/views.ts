// agent-relay script-access D241: the read tools' results, shared by the MCP server and the runtime CLI, so a script
// gets exactly what bridge_agents, bridge_outbox and bridge_sessions return.
import { AWAITING_PRESENCE_TIMEOUT_MS, awaitingCodexPresence, pagePresence } from "./awaiting-reply.js";
import type { AgentHost, BridgeStore } from "./bridge-store.js";
import { claudeSessionsOrNull, type ClaudeSession } from "./claude-wake.js";
import { DEFAULT_PAGE_CHARS, textCost } from "./paging.js";
import { claudePresence, codexTaskPresence, type Presence } from "./presence.js";
import type { WakeTarget } from "./wake-queue.js";

/** agents-view-polish D226: the ChatGPT app is asked for at most 2 s. */
export const CODEX_ASK = { responseTimeoutMs: AWAITING_PRESENCE_TIMEOUT_MS };

/** script-access D244: a script identity has no session to look up. */
export const SCRIPT_PRESENCE: Presence = { state: "unknown", detail: "script identity" };

export interface AgentsViewInput { includeRetired?: boolean; maxChars?: number; afterName?: string }

/** bridge_agents. */
export async function agentsView(store: BridgeStore, { includeRetired, maxChars, afterName }: AgentsViewInput) {
  const waiting = store.waiting();
  const owes = store.owesReplies();
  // agent-relay presence-and-approval D146: read the Claude registry once per listing.
  const claude = await claudeSessionsOrNull();
  const presenceOf = async (host: AgentHost | null): Promise<Presence> =>
    !host ? { state: "unknown", detail: "no recorded host session" }
      : host.app === "script" ? SCRIPT_PRESENCE
      : host.app === "claude" ? claudePresence(host.sessionId, claude)
        : codexTaskPresence(host.sessionId, undefined, CODEX_ASK);
  // agents-view-polish D223: only a call that asks for retired agents, a budget or a cursor is paged; a plain call
  // returns every active agent, as upper layers read it whole.
  const paged = includeRetired === true || maxChars !== undefined || afterName !== undefined;
  let summaries = store.agentSummaries({ includeRetired });
  if (afterName !== undefined) {
    const at = summaries.findIndex((agent) => agent.name === afterName);
    if (at < 0) throw new Error(`No agent named "${afterName}" in this listing; start again without afterName.`);
    summaries = summaries.slice(at + 1);
  }
  // presence-polish D176: a retired identity is never looked up, so a stuck host cannot slow the listing.
  const presences = await Promise.all(summaries.map((agent) =>
    agent.retiredAt ? null : presenceOf(agent.host ?? store.wakes.target(agent.name))));
  const entries = summaries.map((agent, index) => {
    // D223: a retired agent's entry keeps only what identifies it and the fields promised stable.
    if (agent.retiredAt) {
      return {
        name: agent.name, retiredAt: agent.retiredAt, retiredBy: agent.retiredBy, retireNote: agent.retireNote,
        unread: agent.unread, lastActivity: agent.lastActivity, wake: store.wakes.target(agent.name),
        ...(waiting.has(agent.name) ? { waiting: waiting.get(agent.name) } : {}),
      };
    }
    const health = store.wakes.health(agent.name, 1)[0];
    return {
      ...agent,
      ...(presences[index] ? { presence: presences[index] } : {}),
      // agent-relay acceptance-030-gaps D75a: only a Claude host comes from a verified environment.
      host: agent.host ? { ...agent.host, verified: agent.host.app === "claude" } : null,
      wake: store.wakes.target(agent.name),
      ...(health ? { lastPing: { state: health.state, detail: health.detail } } : {}),
      // agent-relay acceptance-030-gaps D77, waiting-list-all-hosts D198: what waits for any host, with the oldest
      // one's time, so any session (or an upper-layer plugin) can tell who is stopped while messages wait.
      ...(waiting.has(agent.name) ? { waiting: waiting.get(agent.name) } : {}),
      // awaiting-reply-view D204: what others wait for this agent to answer; within 2.x only added to.
      ...(owes.has(agent.name) ? { owesReplies: owes.get(agent.name) } : {}),
    };
  });
  if (!paged) return { count: entries.length, agents: entries, hasMore: false };
  const budget = maxChars ?? DEFAULT_PAGE_CHARS;
  let used = 200;
  const agents: typeof entries = [];
  for (const entry of entries) {
    const cost = textCost(JSON.stringify(entry)) + 1;
    if (agents.length && used + cost > budget) break;
    agents.push(entry);
    used += cost;
  }
  const hasMore = agents.length < entries.length;
  return { count: agents.length, agents, hasMore, ...(hasMore ? { nextAfterName: agents.at(-1)!.name } : {}) };
}

export interface OutboxViewInput { agent: string; includeAcknowledged?: boolean; awaitingReply?: boolean; limit?: number }

/** bridge_outbox (the caller's own activity is recorded by the MCP tool, never here). */
export async function outboxView(store: BridgeStore, { agent, includeAcknowledged, awaitingReply, limit }: OutboxViewInput) {
  const page = store.outbox(agent, { includeAcknowledged, awaitingReply, limit });
  if (!awaitingReply) return { agent, ...page };
  // awaiting-reply-view D203: presence only for the recipients on this page; the Claude registry is read once and a
  // Codex lookup waits at most 2 s.
  const claude = await claudeSessionsOrNull();
  const presences = await pagePresence(page.entries.map((entry) => entry.toAgent), (name) => {
    const recipient = store.getAgent(name);
    return recipient ? { host: recipient.host ?? store.wakes.target(name), retired: !!recipient.retiredAt } : undefined;
  }, async (host) => host.app === "script" ? SCRIPT_PRESENCE
    : host.app === "claude" ? claudePresence(host.sessionId, claude)
      : awaitingCodexPresence(host.sessionId));
  return {
    agent,
    ...page,
    entries: page.entries.map((entry) => ({
      ...entry,
      ...(presences.has(entry.toAgent) ? { recipientPresence: presences.get(entry.toAgent) } : {}),
    })),
  };
}

export interface SessionsContext {
  mailboxPath: string;
  thisSession: WakeTarget | null;
  whoami: unknown;
  codexSessionId: string | null;
  channelMode: "enabled" | "off";
}

/** bridge_sessions: the live Claude sessions plus what the caller knows about itself (all null for a script). */
export function sessionsView(claude: ClaudeSession[], context: SessionsContext) {
  return {
    mailboxPath: context.mailboxPath,
    thisSession: context.thisSession,
    whoami: context.whoami,
    claude,
    codexSessionId: context.codexSessionId,
    channelMode: context.channelMode,
    note: "bridge_register with wake: \"auto\" uses thisSession. Codex does not expose its task ID to MCP servers in every version; pass it explicitly when thisSession is null. Background adapters are experimental macOS local interfaces.",
  };
}
