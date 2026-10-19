// agent-relay identity-check: a mailbox name belongs to the host session that registered it.
import type { AgentHost, BridgeAgent } from "./bridge-store.js";

export class IdentityError extends Error {}

function sameHost(a: AgentHost | null, b: AgentHost | null): boolean {
  return !!a && !!b && a.app === b.app && a.sessionId === b.sessionId;
}

/**
 * What this bridge process knows about its caller. `host` is the session the host app put in the environment
 * (Claude sets it; the Codex app-server does not), so it is verified. A name is this session's when it was
 * registered through this process, or when its recorded host is this verified host (survives a bridge restart).
 */
export class CallerIdentity {
  private readonly proven = new Set<string>();

  constructor(readonly host: AgentHost | null) {}

  prove(name: string): void {
    this.proven.add(name);
  }

  /** agent-relay ops-commands (whoami): the names this session may act as, among `agents`. */
  identities(agents: BridgeAgent[]): Array<{ agent: BridgeAgent; provenHere: boolean }> {
    return agents.filter((agent) => this.owns(agent.name, agent))
      .map((agent) => ({ agent, provenHere: this.proven.has(agent.name) }));
  }

  owns(name: string, agent: BridgeAgent | undefined): boolean {
    const recorded = agent?.host ?? null;
    // agent-relay script-access D244: a script identity is no session's; only the runtime CLI sends as it.
    if (recorded?.app === "script") return false;
    // For a verified caller the recorded host decides, so a name taken over by another session stops working here.
    if (this.host && recorded) return sameHost(this.host, recorded);
    return this.proven.has(name);
  }

  /** Refuse to act as `name` unless it is this session's (D37), with the guidance of D39. */
  require(name: string, agent: BridgeAgent | undefined, action: string): void {
    if (this.owns(name, agent)) return;
    const never = "Never guess a session from titles, processes or recent activity.";
    if (!agent) {
      throw new IdentityError(
        `"${name}" is not registered, so this session cannot ${action} it. Call bridge_register with agent ` +
          `"${name}" from this session first (wake: null is fine). ${never}`,
      );
    }
    if (agent.host?.app === "script") {
      throw new IdentityError(
        `"${name}" is a script identity: only the agent-relay runtime CLI (agent-relay send) acts as it, so this ` +
          `session cannot ${action} it. Use this session's own name. ${never}`,
      );
    }
    // agent-relay codex-identity-recovery D209: a Codex caller cannot be verified, so a name recorded for a Codex task is
    // most likely its own name after its bridge process was replaced; say how to prove it again, not to take it over.
    if (!this.host && agent.host?.app === "codex") {
      throw new IdentityError(
        `"${name}" is recorded for a Codex task, and this bridge process cannot tell which task calls it (it is new, for ` +
          `example after the ChatGPT app restarted or the task was reopened), so it cannot ${action} it yet. If ` +
          `"${name}" is this task's own name, call bridge_register with agent "${name}" and wake: {app: "codex", ` +
          `sessionId: "<CODEX_THREAD_ID>"} (or, without pings, host: {app: "codex", sessionId: "<CODEX_THREAD_ID>"}) ` +
          `using this task's own CODEX_THREAD_ID; no takeover is needed for its own name. Then repeat this call. If it ` +
          `is not this task's name, use this task's own name. ${never}`,
      );
    }
    const other = agent.host && !sameHost(this.host, agent.host)
      ? ` It is recorded for another ${agent.host.app} session; registering it here needs takeover: true, which only ` +
        "the user may approve."
      : "";
    throw new IdentityError(
      `"${name}" is not an identity of this session, so it cannot ${action} it: it was not registered through this ` +
        `session's mailbox connection. If it is this session's name (for example after the bridge restarted), call ` +
        `bridge_register with agent "${name}" from this session again.${other} ${never}`,
    );
  }
}
