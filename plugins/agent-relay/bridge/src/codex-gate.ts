// agent-relay codex-gated-wake D66: is the per-turn approval gate known to work for this Codex?
// Before the wake: the ChatGPT app is at least the version the gate was probed on (the real barrier for old apps).
// After the wake: the woken turn's own rollout record shows the gate (a backstop; Codex writes it about 1 s late).
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

/** The ChatGPT app version the gate was probed on (2026-10-08). */
export const MIN_CODEX_APP_VERSION = "26.930";
/** Written next to the mailbox when a woken turn did not show the gate; later Codex wakes are held until removed. */
export const GATE_OFF_FILE = "codex-gate.off";
export const CHATGPT_APP = "/Applications/ChatGPT.app";

export interface TurnContext {
  approvalsReviewer?: string;
  approvalPolicy?: string;
  sandbox?: string;
}

export interface CodexGate {
  /** The ChatGPT app's version, or null when it cannot be read. */
  appVersion(): string | null;
  /** The turn_context Codex recorded for this exact turn of this exact thread, or null when not (yet) recorded. */
  turnContext(threadId: string, turnId: string): TurnContext | null;
}

/** Numeric dotted comparison; anything unreadable is not new enough. */
export function versionAtLeast(version: string | null, minimum = MIN_CODEX_APP_VERSION): boolean {
  if (!version || !/^\d+(\.\d+)*$/.test(version)) return false;
  const have = version.split(".").map(Number);
  const need = minimum.split(".").map(Number);
  for (let i = 0; i < need.length; i++) {
    const a = have[i] ?? 0;
    if (a !== need[i]) return a > need[i];
  }
  return true;
}

/** Why a gated wake must not be sent now, or null when it may. */
export function gateUnverified(gate: CodexGate): string | null {
  const version = gate.appVersion();
  return versionAtLeast(version)
    ? null
    : `the ChatGPT app version ${version ?? "cannot be read"}; gated Codex wake needs ${MIN_CODEX_APP_VERSION} or later`;
}

export function gateApplied(context: TurnContext): boolean {
  return context.approvalsReviewer === "user" && context.approvalPolicy === "on-request" && context.sandbox === "read-only";
}

export interface VerifyOptions {
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

/** Read the woken turn's record every 0.5 s for up to 10 s: ok, mismatch, or missing. */
export async function verifyTurn(gate: CodexGate, threadId: string, turnId: string,
  { intervalMs = 500, timeoutMs = 10_000, sleep = (ms) => new Promise((ok) => setTimeout(ok, ms)) }: VerifyOptions = {},
): Promise<"ok" | "mismatch" | "missing"> {
  for (let waited = 0; ; waited += intervalMs) {
    const context = gate.turnContext(threadId, turnId);
    if (context) return gateApplied(context) ? "ok" : "mismatch";
    if (waited >= timeoutMs) return "missing";
    await sleep(intervalMs);
  }
}

/** Find `rollout-<time>-<threadId>.jsonl` by the exact thread id; never by time or title. */
const ROLLOUT = /^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(.+)\.jsonl$/;

function rolloutFile(sessions: string, threadId: string): string | null {
  const walk = (dir: string, depth: number): string | null => {
    let entries: string[];
    try { entries = readdirSync(dir).sort().reverse(); } catch { return null; }
    for (const name of entries) {
      if (depth === 3) {
        if (ROLLOUT.exec(name)?.[1] === threadId) return join(dir, name);
        continue;
      }
      const found = walk(join(dir, name), depth + 1);
      if (found) return found;
    }
    return null;
  };
  return walk(sessions, 0); // sessions/YYYY/MM/DD/rollout-…
}

export function defaultCodexGate(env: NodeJS.ProcessEnv = process.env): CodexGate {
  const codexHome = env.CODEX_HOME?.trim() || join(env.HOME?.trim() || homedir(), ".codex");
  return {
    appVersion() {
      const plist = join(CHATGPT_APP, "Contents", "Info.plist");
      if (process.platform !== "darwin" || !existsSync(plist)) return null;
      try {
        return execFileSync("/usr/bin/plutil", ["-extract", "CFBundleShortVersionString", "raw", "-o", "-", plist],
          { encoding: "utf8", timeout: 5000 }).trim() || null;
      } catch { return null; }
    },
    turnContext(threadId, turnId) {
      const file = rolloutFile(join(codexHome, "sessions"), threadId);
      if (!file) return null;
      let text: string;
      try { text = readFileSync(file, "utf8"); } catch { return null; }
      for (const line of text.split("\n")) {
        if (!line.includes(turnId)) continue;
        try {
          const record = JSON.parse(line);
          const payload = record?.payload;
          if (record?.type === "turn_context" && payload?.turn_id === turnId) {
            return { approvalsReviewer: payload.approvals_reviewer, approvalPolicy: payload.approval_policy,
              sandbox: payload.sandbox_policy?.type };
          }
        } catch { /* a partly written last line */ }
      }
      return null;
    },
  };
}
