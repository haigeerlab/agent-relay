// A bridge server process driven over stdio, as one host session (agent-relay identity-check tests).
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const projectRoot = dirname(dirname(dirname(fileURLToPath(import.meta.url))));

export interface Session {
  call(name: string, args: Record<string, unknown>): Promise<{ ok: boolean; text: string; json: () => any }>;
  close(): Promise<void>;
}

/** One bridge server process on `dir`'s mailbox, as a Claude session (`claude` id) or a Codex one (no session env). */
export async function session(dir: string, claude: string | null, extraEnv: Record<string, string> = {}): Promise<Session> {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ["--import", "tsx", "src/server.ts"],
    cwd: projectRoot,
    env: {
      PATH: process.env.PATH ?? "",
      HOME: dir,
      BRIDGE_DB_PATH: join(dir, "bridge.sqlite"),
      BRIDGE_BACKUPS: "0",
      XDG_DATA_HOME: join(dir, "data"),
      ...(claude ? { CLAUDE_CODE_SESSION_ID: claude } : {}),
      ...extraEnv,
    },
    stderr: "pipe",
  });
  const client = new Client({ name: `identity-${claude ?? "codex"}`, version: "1.0.0" });
  await client.connect(transport);
  return {
    async call(name, args) {
      const result = await client.callTool({ name, arguments: args });
      const text = (result.content as Array<{ text: string }>)[0]?.text ?? "";
      return { ok: !result.isError, text, json: () => JSON.parse(text) };
    },
    close: () => client.close(),
  };
}

