#!/usr/bin/env node
import { pendingWarning } from "./delivery.js";
import { duplicateWarning } from "./idempotency.js";
import { readBodyFile } from "./body-file.js";
import { basename } from "node:path";
import { CallerIdentity } from "./identity.js";
import type { MessageStatus } from "./bridge-store.js";
import { codexApproval, codexAutoApprovalText } from "./codex-approval.js";
import { randomUUID } from "node:crypto";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { agentNameProblem, checkRecipient } from "./addressing.js";
import { BridgeStore } from "./bridge-store.js";
import { CHANNEL_CAPABILITY, channelSession } from "./claude-channel.js";
import { claudeSessions } from "./claude-wake.js";
import { Housekeeper } from "./housekeeping.js";
import { waitForInbox } from "./inbox-waiter.js";
import { retireAgent } from "./lifecycle.js";
import { BRIDGE_AGENT, CLAUDE_HOLD_EXPLANATION } from "./notices.js";
import { DEFAULT_WAIT_MS, Orchestrator } from "./orchestrator.js";
import { clampLimit, fitMessages } from "./paging.js";
import { defaultDbPath, runsDir } from "./paths.js";
import { buildAskCodexTask, buildCodexReviewTask } from "./simple-tools.js";
import { VERSION } from "./version.js";
import { WakeDispatcher } from "./wake-dispatcher.js";
import type { WakeTarget } from "./wake-queue.js";

/** Everything the MCP protocol reads/writes must stay on stdout; logs go to stderr. */
function log(message: string): void {
  process.stderr.write(`[claude-codex-bridge] ${message}\n`);
}

function jsonResult(payload: unknown) {
  return {
    content: [
      { type: "text" as const, text: JSON.stringify(payload, null, 2) },
    ],
  };
}

/** Claude session liveness. Unknown (non-macOS) counts as live so nothing is misreported. */
async function isClaudeSessionLive(sessionId: string): Promise<boolean> {
  if (process.platform !== "darwin") return true;
  const sessions = await claudeSessions();
  return sessions.some((session) => session.sessionId === sessionId || session.bridgeSessionId === sessionId);
}

/** The app session hosting this MCP process, when the host exposes it. */
function detectSession(env: NodeJS.ProcessEnv = process.env): WakeTarget | null {
  const claude = env.CLAUDE_CODE_SESSION_ID?.trim();
  if (claude) return { app: "claude", sessionId: claude };
  const codex = env.CODEX_THREAD_ID?.trim();
  if (codex) return { app: "codex", sessionId: codex };
  return null;
}

const INSTRUCTIONS = [
  "Local mailbox and Codex worker bridge shared by the Claude and Codex sessions on this machine.",
  "Mailbox: register a unique agent name once with bridge_register (wake: \"auto\" binds this conversation for background pings). If the name was retired, registering is refused: ask the user, then choose a new name or pass reactivate: true. Send with bridge_send; recipients must be registered and any delivery risk comes back as warnings. When pinged, read bridge_inbox, handle the work within the user's existing permissions, bridge_ack after handling, and reply to the sender only when complete, blocked or needing a decision. Never send acknowledgement-only replies. Messages from \"bridge\" are automated notices (delivery failures, retirements, Codex results); do not reply to them. bridge_outbox shows what recipients have not handled yet; bridge_retire closes out a finished task agent. Unbound agents may use bridge_wait during an active turn.",
  "Codex workers: ask_codex, review_with_codex and bridge_orchestrate_codex start a saved Codex session. Reviews run read-only; implementation runs in an isolated worktree with network access off. A call waits up to four minutes. If Codex is still working it returns running_codex, and the result arrives later in your mailbox from \"bridge\" (or call bridge_orchestration_wait). If the status is waiting_for_fable, answer the question and call bridge_continue_codex with the same runId. Independent suggestedChips that the user's task needs may each get their own run (at most three). Verify reported work before calling it done.",
  "Nothing here authorizes commits, pushes, merges, deploys, external sends, credential changes, deletion or production changes.",
].join("\n\n");

function main(): void {
  const dbPath = defaultDbPath();
  const store = new BridgeStore(dbPath);
  const orchestrator = new Orchestrator(store);
  const channelSessionId = channelSession();
  const localAgents: string[] = [];
  // agent-relay identity-check: names this session may act as (D37).
  const caller = new CallerIdentity(detectSession());
  // agent-relay ops-commands (whoami): this session's host, title, project and the identities it may act as.
  const whoami = (claude: Awaited<ReturnType<typeof claudeSessions>>) => {
    const host = caller.host;
    const own = host?.app === "claude"
      ? claude.find((entry) => entry.sessionId === host.sessionId || entry.bridgeSessionId === host.sessionId)
      : undefined;
    const projectDir = process.env.CLAUDE_PROJECT_DIR?.trim() || own?.cwd || null;
    return {
      host: host ? { ...host, verified: true } : null,
      sessionName: own?.name ?? null,
      project: projectDir ? basename(projectDir) : null,
      identities: caller.identities(store.agents()).map(({ agent, provenHere }) => ({
        name: agent.name, provenHere, recordedHost: agent.host, wake: store.wakes.target(agent.name),
      })),
      ...(host ? {} : { note: "This bridge cannot see its session (Codex does not pass one to MCP servers): host, title and project are unknown, and only names registered through this connection are listed." }),
    };
  };
  // agent-relay ops-commands (D45): one message's status, for its sender or recipient only.
  const statusFor = (id: number, as?: string): MessageStatus => {
    const status = store.messageStatus(id);
    if (!status) throw new Error(`No message #${id}.`);
    const { fromAgent, toAgent } = status.message;
    const party = (name: string) => (as === undefined ? caller.owns(name, store.getAgent(name)) : as === name);
    if (!(party(fromAgent) || toAgent === "*" || party(toAgent))) {
      throw new Error(`Message #${id} can be checked only by its sender or recipient ("${fromAgent}", "${toAgent}") from their own session.`);
    }
    return status;
  };
  const defaultAgent = () => localAgents.at(-1) ?? "claude-main";
  const projectFallback = () => {
    const project = process.env.CLAUDE_PROJECT_DIR?.trim();
    if (!project) throw new Error("projectPath is required: this session did not report a project directory.");
    return project;
  };

  log(`store ready at ${dbPath} (schema v${store.migration.to})`);
  if (store.migration.from < store.migration.to) {
    log(`migrated mailbox schema v${store.migration.from} to v${store.migration.to}; backup in ${store.backupDir}`);
  }
  if (store.migration.newer) log("mailbox schema is newer than this bridge build; running in compatible mode");

  const server = new McpServer(
    { name: "claude-codex-bridge", version: VERSION },
    {
      ...(channelSessionId ? { capabilities: { experimental: { [CHANNEL_CAPABILITY]: {} } } } : {}),
      instructions: INSTRUCTIONS,
    },
  );

  const dispatcher = new WakeDispatcher(store, {
    channel: channelSessionId
      ? {
          sessionId: channelSessionId,
          send: (notification) =>
            server.server.notification(notification as unknown as Parameters<typeof server.server.notification>[0]),
        }
      : null,
  });
  const housekeeper = new Housekeeper(store, orchestrator, { runsDir: runsDir(), log });

  const pagingInput = {
    limit: z.number().int().min(1).max(200).optional().describe("Maximum messages to return. Defaults to 25 (30 for threads)."),
    maxChars: z.number().int().min(1000).max(400000).optional().describe("Character budget for the whole result. Defaults to 48000 so MCP hosts never truncate it."),
    maxBodyChars: z.number().int().min(0).max(400000).optional().describe("Preview mode: shorten every body to this many characters."),
  };

  server.registerTool(
    "bridge_register",
    {
      title: "Register agent presence",
      description:
        "Register a unique agent name for this conversation. wake: \"auto\" binds this exact app session for background pings (a Codex task passes {app: \"codex\", sessionId: <its CODEX_THREAD_ID>}); a session can bind only itself; null disables pings; omitted keeps the current binding. A name registered by or bound to another session is refused unless takeover: true, which needs the user's agreement. A retired name is refused unless reactivate: true, which also needs the user's agreement. Registering again after a bridge restart proves the name for this session again.",
      inputSchema: {
        agent: z.string().min(1).describe("Unique readable agent name, e.g. 'review-claude'. Not a session ID."),
        wake: z
          .union([
            z.literal("auto"),
            z.object({ app: z.enum(["codex", "claude"]), sessionId: z.string().min(1).max(128) }),
          ])
          .nullable()
          .optional()
          .describe("\"auto\" detects this conversation's session. Or pass {app, sessionId} (Claude IDs via bridge_sessions; the Codex task ID). null disables pings."),
        capabilities: z
          .array(z.string())
          .optional()
          .describe("Skills this agent offers, e.g. ['review','architecture']. Omitted keeps the existing list."),
        takeover: z.boolean().optional().describe(
          "Move a name registered by or bound to another session to this one. Only after the user agrees."),
        reactivate: z.boolean().optional().describe(
          "Bring back a retired name. Only after the user agrees; the result then says reactivated: true."),
      },
    },
    async ({ agent, capabilities, wake, takeover, reactivate }) => {
      const problem = agentNameProblem(agent);
      if (problem) throw new Error(problem);
      const notes: string[] = [];
      const target = wake === "auto" ? detectSession() : wake;
      if (wake === "auto" && !target) {
        throw new Error("Could not detect this conversation's session. For Codex, pass wake: {app: \"codex\", sessionId: \"<CODEX_THREAD_ID>\"} from this task's own environment; never guess it.");
      }
      // agent-relay identity-check (assumption 4): a Claude session binds only itself; the host it registers from is
      // its verified session, else a Codex session's claimed thread; another session's name or binding needs takeover.
      if (caller.host && target && (target.app !== caller.host.app || target.sessionId !== caller.host.sessionId)) {
        throw new Error(`This session can bind wake only to this session (${caller.host.app}); it cannot bind another session.`);
      }
      if (target?.app === "codex") {
        const approval = codexApproval();
        if (approval.autoApproved) throw new Error(codexAutoApprovalText(approval));
      }
      const host = caller.host ?? (target?.app === "codex" ? target : null);
      const existing = store.getAgent(agent);
      // agent-relay cleanup-gaps D61: a retired name stays retired unless the caller explicitly reactivates it.
      if (existing?.retiredAt && !reactivate) {
        throw new Error(
          `"${agent}" was retired at ${existing.retiredAt}${existing.retiredBy ? ` by ${existing.retiredBy}` : ""}. ` +
            "Ask the user: choose a different name, or pass reactivate: true only after the user agrees to bring it back.",
        );
      }
      if (existing?.retiredAt) notes.push(`"${agent}" was retired at ${existing.retiredAt} and is reactivated.`);
      const current = store.wakes.target(agent);
      const owner = existing?.host ?? null;
      const ownerConflict = !!owner && (!host || owner.app !== host.app || owner.sessionId !== host.sessionId);
      const bindingConflict = !!target && !!current && (current.app !== target.app || current.sessionId !== target.sessionId);
      if ((ownerConflict || bindingConflict) && !takeover) {
        const other = ownerConflict ? owner! : current!;
        const running = other.app === "claude" ? ((await isClaudeSessionLive(other.sessionId)) ? " (still running)" : " (no longer running)") : "";
        const codexHint = !host && owner?.app === "codex"
          ? " If it is this Codex task's own name, register again with wake: {app: \"codex\", sessionId: \"<CODEX_THREAD_ID>\"}."
          : "";
        throw new Error(
          `"${agent}" is ${ownerConflict ? "registered by" : "bound to"} another ${other.app} session${running}.${codexHint} ` +
            "Choose a different name, or pass takeover: true only after the user agrees to move it to this session.",
        );
      }
      if (takeover && (ownerConflict || bindingConflict)) notes.push(`"${agent}" was taken over from another session.`);
      if (wake !== undefined) store.wakes.bind(agent, target ?? null);
      const registered = store.register(agent, capabilities, takeover && ownerConflict ? host : host ?? undefined);
      caller.prove(agent);
      localAgents.splice(0, localAgents.length, ...localAgents.filter((name) => name !== agent), agent);
      const unread = store.countUnread(agent);
      return jsonResult({
        ...registered,
        wake: store.wakes.target(agent),
        ...(existing?.retiredAt ? { reactivated: true } : {}),
        unread,
        ...(unread > 0 ? { next: `${unread} unread message(s) are waiting. Read them with bridge_inbox.` } : {}),
        ...(notes.length ? { notes } : {}),
      });
    },
  );

  server.registerTool(
    "bridge_send",
    {
      title: "Send a message",
      description:
        "Save a message, then ping its bound recipient in the background. The recipient must be registered (use allowUnregistered only when it will register later). The result carries warnings when the recipient is unlikely to pick the message up. Broadcasts and wake:false sends do not ping anyone. A direct message reports deliveryState: queued, sending, accepted, failed, unknown or expired. Exactly-once is not promised: an unconfirmed ping is reported unknown and never re-sent, and a message still queued after its timeout (default 24 h) expires and is never delivered. Pings to one recipient go out one at a time in message order; a recipient holding BRIDGE_MAX_PENDING_PER_RECIPIENT (default 100) undelivered messages refuses new sends.",
      inputSchema: {
        wake: z.boolean().optional().describe("Ping a bound direct recipient. Defaults true. False saves silently."),
        from: z.string().min(1).describe("Sender agent name."),
        to: z.string().min(1).describe("Recipient agent name, or '*' to broadcast."),
        body: z.string().min(1).optional().describe("Message content. Give exactly one of body and bodyFile."),
        bodyFile: z.string().min(1).optional().describe(
          "Absolute path of a UTF-8 text file (regular file you own, at most 256 KiB) whose content is sent unchanged, so nothing passes through shell quoting. Give exactly one of body and bodyFile."),
        threadId: z.string().optional().describe("Optional conversation thread identifier."),
        idempotencyKey: z.string().optional().describe(
          "Optional retry key. A retry with the same key and content returns the stored message (duplicate: true) and pings nobody; the same key with a different recipient, body or thread is refused — the earlier message is already stored, so no resend is needed."),
        replyTo: z.number().int().positive().optional().describe(
          "Id of the message this one answers. The reply goes on that message's thread (omit threadId, or give the same one), and the sender's outbox lists it under the original."),
        allowUnregistered: z.boolean().optional().describe("Deliver even if the recipient is unknown or retired."),
        expiresInSeconds: z.number().int().min(60).max(604800).optional().describe(
          "Queue timeout for a direct message: if still undelivered after this many seconds it expires and is never delivered. Default 24 h (BRIDGE_QUEUE_TIMEOUT_MS)."),
      },
    },
    async ({ from, to, body: text, bodyFile, threadId, idempotencyKey, replyTo, wake, allowUnregistered, expiresInSeconds }) => {
      if ((text === undefined) === (bodyFile === undefined)) throw new Error("Give exactly one of body and bodyFile.");
      const body = text ?? readBodyFile(bodyFile as string);
      if (from === BRIDGE_AGENT) throw new Error(`"${BRIDGE_AGENT}" is reserved for automated notices.`);
      caller.require(from, store.getAgent(from), "send as");
      const check = await checkRecipient(store, to, { allowUnregistered, isClaudeSessionLive });
      if (!check.ok) throw new Error(check.error);
      const warnings = [...check.warnings];
      const { message, duplicate } = store.deliver({
        wake,
        fromAgent: from,
        toAgent: to,
        body,
        threadId: threadId ?? null,
        idempotencyKey: idempotencyKey ?? null,
        replyTo: replyTo ?? null,
        expiresInSeconds,
      });
      store.touch(from);
      if (duplicate) warnings.push(duplicateWarning(message.id));
      if (to !== "*") {
        const capWarning = pendingWarning(store.database, to);
        if (capWarning) warnings.push(capWarning);
      }
      await dispatcher.flush();
      return jsonResult({
        ...message,
        wake: store.wakes.forMessage(message.id),
        ...(duplicate ? { duplicate } : {}),
        ...(warnings.length ? { warnings } : {}),
      });
    },
  );

  server.registerTool("bridge_sessions", {
    title: "Discover local wake targets",
    description: "Read live Claude session IDs and this conversation's own session when the host exposes it. Does not wake anything or read conversation content.",
    inputSchema: {},
  }, async () => {
    const claude = await claudeSessions();
    return jsonResult({
    mailboxPath: dbPath,
    thisSession: detectSession(),
    whoami: whoami(claude),
    claude,
    codexSessionId: process.env.CODEX_THREAD_ID ?? null,
    channelMode: channelSessionId ? "enabled" : "off",
    note: "bridge_register with wake: \"auto\" uses thisSession. Codex does not expose its task ID to MCP servers in every version; pass it explicitly when thisSession is null. Background adapters are experimental macOS local interfaces.",
    });
  });

  server.registerTool("bridge_wake_status", {
    title: "Inspect background ping delivery",
    description: "Read up to 100 recent wake receipts with a per-state summary. Accepted means the app accepted a ping, not that the work is complete. Held/refused respect app permission checks; unknown outcomes are never replayed automatically.",
    inputSchema: {
      agent: z.string().min(1).optional(),
      messageId: z.number().int().positive().optional().describe(
        "Status of one message you sent or received: delivery state, ping, acknowledgement, replies and outcome (pending, acknowledged, replied, failed, expired)."),
    },
  }, async ({ agent, messageId }) => {
    if (messageId !== undefined) return jsonResult(statusFor(messageId));
    const jobs = store.wakes.list(agent);
    const summary: Record<string, number> = {};
    for (const job of jobs) summary[job.state] = (summary[job.state] ?? 0) + 1;
    const claudeHolds = jobs.some((job) => job.target.app === "claude" && (job.state === "held" || /expired|held/i.test(job.detail)));
    return jsonResult({ summary, ...(claudeHolds ? { explanation: CLAUDE_HOLD_EXPLANATION } : {}), jobs });
  });

  server.registerTool(
    "bridge_inbox",
    {
      title: "Read inbox",
      description:
        "List messages addressed to an agent, oldest first, in pages that fit the host's output limit. Acknowledged messages are hidden by default. When hasMore is true, acknowledge handled messages and read again, or pass afterId.",
      inputSchema: {
        agent: z.string().min(1).describe("Agent whose inbox to read."),
        includeAcknowledged: z.boolean().optional().describe("Include messages this agent has already acknowledged."),
        fromAgent: z.string().min(1).optional().describe("Only messages from this sender."),
        threadId: z.string().min(1).optional().describe("Only messages on this thread."),
        afterId: z.number().int().min(0).optional().describe("Only messages with a larger id (paging cursor)."),
        includeExpired: z.boolean().optional().describe(
          "Also list messages that expired before delivery. They are history: never act on them."),
        ...pagingInput,
      },
    },
    async ({ agent, includeAcknowledged, fromAgent, threadId, afterId, includeExpired, limit, maxChars, maxBodyChars }) => {
      const page = store.inboxPage(agent, { includeAcknowledged, fromAgent, threadId, afterId, includeExpired, limit, maxChars, maxBodyChars });
      store.wakes.recordRead(agent, page.messages.map((message) => message.id));
      store.touch(agent);
      return jsonResult({ agent, ...page });
    },
  );

  server.registerTool(
    "bridge_wait",
    {
      title: "Wait for the next bridge message",
      description:
        "Keep this agent turn alive until a matching bridge message arrives, for agents without background pings. It cannot wake a chat whose turn has already ended, so call it before going idle. After handling and replying, call bridge_wait again while the coordination thread is active.",
      inputSchema: {
        agent: z.string().min(1).describe("Agent whose inbox should wake this turn."),
        fromAgent: z.string().min(1).optional().describe("Optional sender filter."),
        threadId: z.string().min(1).optional().describe("Optional coordination thread filter."),
        timeoutSeconds: z.number().int().min(1).max(290).optional().describe("How long to keep the MCP call open. Defaults to 285 seconds so common five-minute host limits do not cut it off."),
        acknowledge: z.boolean().optional().describe("Mark returned messages handled before returning. Defaults true; history is preserved."),
        messageId: z.number().int().positive().optional().describe(
          "Instead of new inbox messages, wait for this message's outcome (acknowledged, replied, failed or expired). agent must be its sender or recipient; nothing is acknowledged."),
        limit: pagingInput.limit,
        maxChars: pagingInput.maxChars,
      },
    },
    async ({ agent, fromAgent, threadId, timeoutSeconds, acknowledge, limit, maxChars, messageId }) => {
      if (messageId !== undefined) {
        caller.require(agent, store.getAgent(agent), "wait as");
        const deadline = Date.now() + (timeoutSeconds ?? 285) * 1000;
        let status = statusFor(messageId, agent);
        while (status.outcome === "pending" && Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, Math.min(250, Math.max(0, deadline - Date.now()))));
          status = statusFor(messageId, agent);
        }
        return jsonResult({ timedOut: status.outcome === "pending", ...status });
      }
      if (acknowledge ?? true) caller.require(agent, store.getAgent(agent), "acknowledge messages for");
      const max = clampLimit(limit);
      store.touch(agent);
      const result = await waitForInbox(store, {
        agent,
        fromAgent,
        threadId,
        timeoutMs: (timeoutSeconds ?? 285) * 1000,
        limit: max + 1,
      });
      const fitted = fitMessages(result.messages.slice(0, max), { maxChars });
      const ids = fitted.messages.map((message) => message.id);
      const acknowledged = (acknowledge ?? true) && ids.length > 0 ? store.ack(agent, ids) : 0;
      store.wakes.recordRead(agent, ids);
      return jsonResult({
        timedOut: result.timedOut,
        count: fitted.messages.length,
        acknowledged,
        hasMore: result.messages.length > max || fitted.omitted > 0,
        messages: fitted.messages,
        nextAction: result.timedOut
          ? "If the coordination thread is still active, call bridge_wait again."
          : "Handle these messages, reply with bridge_send, then call bridge_wait again before ending the turn.",
      });
    },
  );

  server.registerTool(
    "bridge_ack",
    {
      title: "Acknowledge messages",
      description: "Mark messages as handled for an agent so they drop out of the unread inbox. History is kept.",
      inputSchema: {
        agent: z.string().min(1).describe("Agent acknowledging the messages."),
        ids: z.array(z.number().int().positive()).min(1).describe("Message ids to acknowledge."),
      },
    },
    async ({ agent, ids }) => {
      caller.require(agent, store.getAgent(agent), "acknowledge messages for");
      const acknowledged = store.ack(agent, ids);
      store.touch(agent);
      return jsonResult({ acknowledged, remainingUnread: store.countUnread(agent) });
    },
  );

  server.registerTool(
    "bridge_thread",
    {
      title: "Read a thread",
      description:
        "Read one page of a conversation thread. Without a cursor it returns the most recent messages; pass beforeId (olderBeforeId) to page back or afterId (newerAfterId) to page forward.",
      inputSchema: {
        threadId: z.string().min(1).describe("Thread identifier to fetch."),
        beforeId: z.number().int().min(1).optional().describe("Return messages older than this id."),
        afterId: z.number().int().min(0).optional().describe("Return messages newer than this id."),
        ...pagingInput,
      },
    },
    async ({ threadId, beforeId, afterId, limit, maxChars, maxBodyChars }) =>
      jsonResult(store.threadPage(threadId, { beforeId, afterId, limit, maxChars, maxBodyChars })),
  );

  server.registerTool(
    "bridge_agents",
    {
      title: "List agents",
      description: "List registered agents with unread counts, last activity, ping binding and recent ping health. Retired agents are hidden unless requested.",
      inputSchema: {
        includeRetired: z.boolean().optional().describe("Include retired agents."),
      },
    },
    async ({ includeRetired }) => {
      const agents = store.agentSummaries({ includeRetired }).map((agent) => {
        const health = store.wakes.health(agent.name, 1)[0];
        return {
          ...agent,
          wake: store.wakes.target(agent.name),
          ...(health ? { lastPing: { state: health.state, detail: health.detail } } : {}),
        };
      });
      return jsonResult({ count: agents.length, agents });
    },
  );

  server.registerTool(
    "bridge_outbox",
    {
      title: "Check sent messages",
      description: "List direct messages an agent sent that the recipient has not acknowledged yet (newest first), with ping outcome, delivery state (queued, sending, accepted, failed, unknown, expired) and whether the recipient is active, retired or unknown.",
      inputSchema: {
        agent: z.string().min(1).describe("Sender whose outbox to read."),
        includeAcknowledged: z.boolean().optional().describe("Include messages the recipient already acknowledged."),
        limit: z.number().int().min(1).max(200).optional().describe("Maximum entries. Defaults to 30."),
      },
    },
    async ({ agent, includeAcknowledged, limit }) => {
      store.touch(agent);
      return jsonResult({ agent, ...store.outbox(agent, { includeAcknowledged, limit }) });
    },
  );

  server.registerTool(
    "bridge_retire",
    {
      title: "Retire a finished agent",
      description:
        "Retire an agent whose task is over: its pings stop, its unhandled messages are closed with a recorded reason (history is kept), and recently active senders get one notice listing what was closed. The name then stays retired: registering it again needs reactivate: true and the user's agreement.",
      inputSchema: {
        agent: z.string().min(1).describe("Agent to retire."),
        by: z.string().min(1).optional().describe("Who is retiring it. Defaults to this conversation's agent."),
        note: z.string().max(500).optional().describe("Short reason, e.g. 'task merged'."),
        closeBacklog: z.boolean().optional().describe("Close unhandled messages. Defaults true."),
        notifySenders: z.boolean().optional().describe("Tell recently active senders what was closed. Defaults true."),
      },
    },
    async ({ agent, by, note, closeBacklog, notifySenders }) =>
      jsonResult(retireAgent(store, agent, { by: by ?? localAgents.at(-1) ?? "operator", note, closeBacklog, notifySenders })),
  );

  const waitSeconds = z
    .number()
    .int()
    .min(0)
    .max(285)
    .optional()
    .describe("How long this call waits for Codex. Defaults to 240 seconds. If Codex is still working, the result arrives in the coordinator's mailbox.");
  const waitMs = (seconds: number | undefined) => (seconds === undefined ? DEFAULT_WAIT_MS : seconds * 1000);

  server.registerTool(
    "ask_codex",
    {
      title: "Ask Codex",
      description:
        "Send one bounded implementation, investigation, or verification task to a saved Codex worker in an isolated worktree. This is the simple everyday entry point; no mailbox or thread management is required.",
      inputSchema: {
        projectPath: z.string().min(1).optional().describe("Absolute path to the repository. Defaults to this session's project directory."),
        request: z.string().min(1).describe("What Codex should do."),
        coordinatorAgent: z.string().min(1).optional().describe("Agent that receives the result. Defaults to this conversation's registered agent, else claude-main."),
        threadId: z.string().min(1).optional().describe("Optional stable task ID. Generated when omitted."),
        useWorktree: z.boolean().optional().describe("Use an isolated Git worktree. Defaults true."),
        includeUncommitted: z.boolean().optional().describe("Copy the main checkout's uncommitted changes into the worktree."),
        waitSeconds,
      },
    },
    async ({ projectPath, request, coordinatorAgent, threadId, useWorktree, includeUncommitted, waitSeconds: seconds }) =>
      jsonResult(
        await orchestrator.start({
          coordinatorAgent: coordinatorAgent ?? defaultAgent(),
          projectPath: projectPath ?? projectFallback(),
          task: buildAskCodexTask(request),
          threadId: threadId ?? `ask-codex-${randomUUID()}`,
          useWorktree: useWorktree ?? true,
          includeUncommitted,
          maxRounds: 4,
          waitMs: waitMs(seconds),
        }),
      ),
  );

  server.registerTool(
    "review_with_codex",
    {
      title: "Review with Codex",
      description:
        "Ask Codex for a read-only repository review with evidence and actionable findings. Codex runs in a read-only sandbox and the bridge reports whether the workspace changed.",
      inputSchema: {
        projectPath: z.string().min(1).optional().describe("Absolute path to the repository. Defaults to this session's project directory."),
        focus: z.string().optional().describe("Optional review focus, such as security, a PR, or a subsystem."),
        coordinatorAgent: z.string().min(1).optional().describe("Agent that receives the result. Defaults to this conversation's registered agent, else claude-main."),
        threadId: z.string().min(1).optional().describe("Optional stable task ID. Generated when omitted."),
        waitSeconds,
      },
    },
    async ({ projectPath, focus, coordinatorAgent, threadId, waitSeconds: seconds }) =>
      jsonResult(
        await orchestrator.start({
          coordinatorAgent: coordinatorAgent ?? defaultAgent(),
          projectPath: projectPath ?? projectFallback(),
          task: buildCodexReviewTask(focus),
          threadId: threadId ?? `codex-review-${randomUUID()}`,
          useWorktree: false,
          sandbox: "read-only",
          maxRounds: 1,
          waitMs: waitMs(seconds),
        }),
      ),
  );

  server.registerTool(
    "bridge_orchestrate_codex",
    {
      title: "Start an autonomous Codex implementation run",
      description:
        "Start a saved Codex worker in an isolated git worktree (network off) and wait up to waitSeconds for its structured result. If status is waiting_for_fable, answer the question and call bridge_continue_codex. If it is running_codex, the result arrives in the coordinator's mailbox. Independent calls create separate runs. This tool never grants permission to commit, push, deploy, publish, send externally, change credentials, delete data, or mutate production.",
      inputSchema: {
        coordinatorAgent: z.string().min(1).optional().describe("Agent that receives the result. Defaults to this conversation's registered agent, else claude-main."),
        projectPath: z.string().min(1).optional().describe("Absolute path to the git repository. Defaults to this session's project directory."),
        task: z.string().min(1).describe("Self-contained implementation or verification task."),
        threadId: z.string().min(1).describe("Stable task/thread identifier."),
        useWorktree: z.boolean().optional().describe("Create an isolated git worktree. Defaults true."),
        includeUncommitted: z.boolean().optional().describe("Copy the main checkout's uncommitted changes into the worktree."),
        maxRounds: z.number().int().min(1).max(12).optional().describe("Maximum coordinator/Codex turns. Defaults 6."),
        waitSeconds,
      },
    },
    async ({ coordinatorAgent, projectPath, task, threadId, useWorktree, includeUncommitted, maxRounds, waitSeconds: seconds }) =>
      jsonResult(
        await orchestrator.start({
          coordinatorAgent: coordinatorAgent ?? defaultAgent(),
          projectPath: projectPath ?? projectFallback(),
          task,
          threadId,
          useWorktree: useWorktree ?? true,
          includeUncommitted,
          maxRounds: maxRounds ?? 6,
          waitMs: waitMs(seconds),
        }),
      ),
  );

  server.registerTool(
    "bridge_continue_codex",
    {
      title: "Continue Codex with the coordinator's answer",
      description:
        "Resume the exact saved Codex session and worktree after Codex asked for a decision (status waiting_for_fable). The sandbox from the first turn is kept. Continue until completed, blocked, failed, or the round limit is reached.",
      inputSchema: {
        runId: z.string().uuid().describe("Run ID returned by the orchestration tool."),
        fableAnswer: z.string().min(1).describe("The coordinator's concrete answer to Codex's question."),
        waitSeconds,
      },
    },
    async ({ runId, fableAnswer, waitSeconds: seconds }) =>
      jsonResult(await orchestrator.continueWithFable(runId, fableAnswer, waitMs(seconds))),
  );

  server.registerTool(
    "bridge_orchestration_wait",
    {
      title: "Wait for a Codex run",
      description: "Wait up to timeoutSeconds for a running Codex run to finish its current round, then return its result. Works for runs started by any bridge process.",
      inputSchema: {
        runId: z.string().uuid().describe("Orchestration run ID."),
        timeoutSeconds: z.number().int().min(0).max(285).optional().describe("Defaults to 240 seconds."),
      },
    },
    async ({ runId, timeoutSeconds }) => jsonResult(await orchestrator.wait(runId, waitMs(timeoutSeconds))),
  );

  server.registerTool(
    "bridge_orchestration_status",
    {
      title: "Inspect an orchestration run",
      description: "Recover durable run state and its audit events after a restart or when checking progress.",
      inputSchema: {
        runId: z.string().uuid().describe("Orchestration run ID."),
      },
    },
    async ({ runId }) => jsonResult(orchestrator.status(runId)),
  );

  const transport = new StdioServerTransport();

  let shuttingDown = false;
  const shutdown = (signal: string): void => {
    if (shuttingDown) return;
    shuttingDown = true;
    log(`received ${signal}, shutting down`);
    housekeeper.stop();
    orchestrator.close();
    void dispatcher.close().then(() => server.close()).finally(() => {
      store.close();
      process.exit(0);
    });
  };
  server.server.onclose = () => shutdown("transport closed");
  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));

  server
    .connect(transport)
    .then(() => {
      dispatcher.start();
      housekeeper.start();
      log(`connected over stdio (v${VERSION}${channelSessionId ? ", Claude channel mode" : ""})`);
    })
    .catch((error: unknown) => {
      log(`fatal: ${error instanceof Error ? error.stack ?? error.message : String(error)}`);
      housekeeper.stop();
      void dispatcher.close().finally(() => { store.close(); process.exit(1); });
    });
}

main();
