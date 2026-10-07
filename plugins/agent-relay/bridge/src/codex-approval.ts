// agent-relay identity-check (assumption 6, D38): is Codex running with auto-approval? Read only, never written.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface CodexApproval {
  autoApproved: boolean;
  reason: string;
}

const KEYS = new Set(["approvals_reviewer", "approval_policy"]);
const QUOTED = /^\s*([A-Za-z_]+)\s*=\s*(?:"([^"]*)"|'([^']*)')\s*(?:#.*)?$/;
const ANY_KEY = /^\s*([A-Za-z_]+)\s*=/;

/**
 * Codex counts as auto-approved when its top-level `approvals_reviewer` is "guardian_subagent" or `approval_policy`
 * is "never" in `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`). A missing file means Codex's defaults
 * (not auto-approved). An unreadable file or an unparsable value of those keys counts as auto-approved (fail closed).
 * `[profiles.*]` overrides are not evaluated.
 */
export function codexApproval(env: NodeJS.ProcessEnv = process.env): CodexApproval {
  const path = join(env.CODEX_HOME?.trim() || join(env.HOME?.trim() || homedir(), ".codex"), "config.toml");
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { autoApproved: false, reason: `${path} does not exist (Codex defaults)` };
    return { autoApproved: true, reason: `${path} could not be read, so auto-approval cannot be ruled out` };
  }
  for (const line of text.split(/\r?\n/)) {
    if (/^\s*\[/.test(line)) break; // only top-level keys; tables (profiles, servers) follow
    const key = ANY_KEY.exec(line)?.[1];
    if (!key || !KEYS.has(key)) continue;
    const match = QUOTED.exec(line);
    if (!match) return { autoApproved: true, reason: `${path}: ${key} has a value that cannot be read, so auto-approval cannot be ruled out` };
    const value = match[2] ?? match[3];
    if (key === "approvals_reviewer" && value === "guardian_subagent") {
      return { autoApproved: true, reason: `${path} sets approvals_reviewer = "guardian_subagent" (AI auto-review)` };
    }
    if (key === "approval_policy" && value === "never") {
      return { autoApproved: true, reason: `${path} sets approval_policy = "never"` };
    }
  }
  return { autoApproved: false, reason: `${path} asks a person for approval` };
}

/** Why a Codex session under auto-approval is not bound or pinged, and how the user can change it. */
export function codexAutoApprovalText(approval: CodexApproval): string {
  return `Codex runs with auto-approval: ${approval.reason}. A woken Codex turn would act on mailbox messages with ` +
    "nobody approving, so the bridge does not bind or ping Codex sessions now. To allow it, set the Codex approval " +
    "selector to 请求批准 (approvals_reviewer not guardian_subagent, approval_policy not never); the bridge never " +
    "changes that setting.";
}
