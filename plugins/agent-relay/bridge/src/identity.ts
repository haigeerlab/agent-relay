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

  owns(name: string, agent: BridgeAgent | undefined): boolean {
    const recorded = agent?.host ?? null;
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
