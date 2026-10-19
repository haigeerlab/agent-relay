// A fake ChatGPT app IPC socket for the codex-approval-presence tests: completes the handshake, answers thread-owner
// discovery as configured, pushes follower frames when a thread is followed, and records every frame it receives.
import { chmodSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { createServer, type Server, type Socket } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";

export interface FakeAppOptions {
  /** Discovery answer: an owner client id, none, or no answer at all. */
  owner?: "owner" | "none" | "silent";
  /** Follower frames to push (as `params` of `thread-stream-state-changed`) when the thread is followed. */
  onFollow?: (conversationId: string) => Array<Record<string, unknown> | { raw: Buffer }>;
  /** Directory to put `.codex/ipc/ipc.sock` under (a fake HOME); a fresh temporary one when absent. */
  home?: string;
}

export interface FakeApp {
  path: string;
  home: string;
  /** Every frame the client sent, in order. */
  received: Array<Record<string, any>>;
  close(): Promise<void>;
}

function frame(packet: unknown): Buffer {
  const body = Buffer.from(JSON.stringify(packet));
  const header = Buffer.alloc(4); header.writeUInt32LE(body.length);
  return Buffer.concat([header, body]);
}

export async function fakeCodexApp(options: FakeAppOptions = {}): Promise<FakeApp> {
  const home = options.home ?? mkdtempSync(join(tmpdir(), "codex-app-"));
  const dir = join(home, ".codex", "ipc");
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  chmodSync(join(home, ".codex"), 0o700);
  chmodSync(dir, 0o700);
  const path = join(dir, "ipc.sock");
  const received: Array<Record<string, any>> = [];
  const sockets = new Set<Socket>();
  const server: Server = createServer(socket => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
    let buffer = Buffer.alloc(0);
    socket.on("error", () => {});
    socket.on("data", chunk => {
      buffer = Buffer.concat([buffer, chunk]);
      while (buffer.length >= 4) {
        const size = buffer.readUInt32LE(0);
        if (buffer.length < size + 4) return;
        const r = JSON.parse(buffer.subarray(4, size + 4).toString());
        buffer = buffer.subarray(size + 4);
        received.push(r);
        if (r.type === "request" && r.method === "initialize") {
          socket.write(frame({ type: "response", requestId: r.requestId, resultType: "success",
            result: { clientId: "test-client" } }));
        } else if (r.type === "request" && r.method === "thread-owner-discovery") {
          if (options.owner === "silent") continue;
          socket.write(frame({ type: "response", requestId: r.requestId, resultType: "success", result: {},
            ...((options.owner ?? "owner") === "owner" ? { handledByClientId: "owner" } : {}) }));
        } else if (r.type === "broadcast" && r.method === "thread-stream-following-changed" && r.params?.following) {
          for (const params of options.onFollow?.(r.params.conversationId) ?? []) {
            socket.write("raw" in params && Buffer.isBuffer(params.raw) ? params.raw
              : frame({ type: "broadcast", method: "thread-stream-state-changed", sourceClientId: "owner", version: 1,
                params }));
          }
        }
      }
    });
  });
  await new Promise<void>(ok => server.listen(path, ok));
  chmodSync(path, 0o600);
  return {
    path, home, received,
    async close() {
      for (const socket of sockets) socket.destroy();
      await new Promise<void>(ok => server.close(() => ok()));
      if (!options.home) rmSync(home, { recursive: true, force: true });
    },
  };
}

/** A follower snapshot of `conversationState`. */
export function snapshot(conversationId: string, conversationState: Record<string, unknown>): Record<string, unknown> {
  return { conversationId, hostId: "local", change: { type: "snapshot", revision: 1, conversationState } };
}
