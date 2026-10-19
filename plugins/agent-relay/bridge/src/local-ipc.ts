import { dirname } from "node:path";
import { lstat } from "node:fs/promises";
import { createConnection, type Socket } from "node:net";
import { randomUUID } from "node:crypto";

export async function privatePath(path: string, kind: "socket" | "file" | "directory"): Promise<void> {
  const stat = await lstat(path);
  const matches = kind === "socket" ? stat.isSocket() : kind === "file" ? stat.isFile() : stat.isDirectory();
  if (!matches || stat.isSymbolicLink() || stat.uid !== process.getuid?.() || (stat.mode & 0o077) !== 0) {
    throw new Error("Local IPC path has unexpected ownership, type or permissions");
  }
}

export class IpcError extends Error {
  constructor(message: string, readonly sent = false, readonly timedOut = false) { super(message); }
}

/** How long a request waits for the app's answer. */
export const IPC_RESPONSE_TIMEOUT_MS = 10_000;

type Packet = Record<string, any>;
export class CodexIpc {
  private socket: Socket | null = null;
  private buffer = Buffer.alloc(0);
  private clientId = "initializing-client";
  /** Bytes of an oversized frame still to discard (codex-approval-presence rework, #8194). */
  private skip = 0;
  private pending = new Map<string, { resolve: (p: Packet) => void; reject: (e: Error) => void; timer: NodeJS.Timeout }>();
  private followers = new Map<string, { resolve: (change: Packet) => void; reject: (e: Error) => void; timer: NodeJS.Timeout }>();

  constructor(private readonly options: { responseTimeoutMs?: number } = {}) {}

  async connect(path: string): Promise<void> {
    await privatePath(dirname(path), "directory");
    await privatePath(path, "socket");
    await new Promise<void>((resolve, reject) => {
      const socket = this.socket = createConnection(path);
      const timer = setTimeout(() => { socket.destroy(); reject(new IpcError("Codex connection timed out")); }, 3000);
      socket.once("connect", () => { clearTimeout(timer); resolve(); });
      socket.on("error", () => { clearTimeout(timer); reject(new IpcError("Codex connection unavailable")); this.fail(); });
      socket.on("close", () => this.fail());
      socket.on("data", chunk => {
        try { this.read(chunk); } catch { socket.destroy(); this.fail(); }
      });
    });
    // agent-relay legacy-cli-cleanup D96: the app interface knows this client by its upstream name; not renamed.
    const reply = await this.request("initialize", { clientType: "claude-codex-bridge" });
    if (reply.resultType !== "success" || typeof reply.result?.clientId !== "string") {
      throw new IpcError("Codex IPC initialization rejected");
    }
    this.clientId = reply.result.clientId;
  }

  private fail(): void {
    for (const p of this.pending.values()) {
      clearTimeout(p.timer); p.reject(new IpcError("Codex IPC response unavailable", true));
    }
    this.pending.clear();
    for (const f of this.followers.values()) {
      clearTimeout(f.timer); f.reject(new IpcError("Codex IPC response unavailable", true));
    }
    this.followers.clear();
  }

  private write(packet: Packet): void {
    const body = Buffer.from(JSON.stringify(packet));
    const header = Buffer.alloc(4);
    header.writeUInt32LE(body.length);
    this.socket!.write(Buffer.concat([header, body]));
  }

  private read(chunk: Buffer): void {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (true) {
      if (this.skip > 0) {
        const n = Math.min(this.skip, this.buffer.length);
        this.buffer = this.buffer.subarray(n);
        this.skip -= n;
        if (this.skip > 0) return;
      }
      if (this.buffer.length < 4) return;
      const length = this.buffer.readUInt32LE(0);
      if (length > 8 * 1024 * 1024) {
        // codex-approval-presence rework (#8194): an oversized frame (a long conversation's snapshot) is discarded
        // without buffering it and without dropping the connection, so the caller can still unfollow; only the
        // follower waiters fail.
        this.skip = length;
        this.buffer = this.buffer.subarray(4);
        for (const f of this.followers.values()) {
          clearTimeout(f.timer); f.reject(new IpcError("Codex IPC frame too large", true));
        }
        this.followers.clear();
        continue;
      }
      if (this.buffer.length < length + 4) return;
      const p = JSON.parse(this.buffer.subarray(4, length + 4).toString());
      this.buffer = this.buffer.subarray(length + 4);
      if (p.type === "client-discovery-request") {
        this.write({ type: "client-discovery-response", requestId: p.requestId, response: { canHandle: false } });
      } else if (p.type === "response") {
        const waiting = this.pending.get(p.requestId);
        if (!waiting) continue;
        this.pending.delete(p.requestId);
        clearTimeout(waiting.timer); waiting.resolve(p);
      } else if (p.type === "broadcast" && p.method === "thread-stream-state-changed"
        && typeof p.params?.conversationId === "string" && this.followers.has(p.params.conversationId)) {
        // codex-approval-presence D234: only the change for a thread this client follows reaches its one waiter.
        const follower = this.followers.get(p.params.conversationId)!;
        this.followers.delete(p.params.conversationId);
        clearTimeout(follower.timer); follower.resolve(p.params.change ?? {});
      }
      // Never publish unsolicited app broadcasts or conversation content; a followed thread's change goes only to the
      // caller that asked for it (codex-approval-presence D234).
    }
  }

  request(method: string, params: Packet, version = 0, targetClientId?: string): Promise<Packet> {
    if (!this.socket || this.socket.destroyed) return Promise.reject(new IpcError("Codex disconnected"));
    return new Promise((resolve, reject) => {
      const requestId = randomUUID();
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new IpcError("Codex IPC response timed out", true, true));
      }, this.options.responseTimeoutMs ?? IPC_RESPONSE_TIMEOUT_MS);
      this.pending.set(requestId, { resolve, reject, timer });
      this.write({ type: "request", requestId, sourceClientId: this.clientId, version, method, params,
        ...(targetClientId ? { targetClientId } : {}) });
    });
  }

  /** codex-approval-presence D235: a broadcast to the given clients (used only to follow and unfollow a thread). */
  broadcast(method: string, params: Packet, targetClientIds: string[], version = 1): void {
    if (!this.socket || this.socket.destroyed) return;
    this.write({ type: "broadcast", method, sourceClientId: this.clientId, version, targetClientIds, params });
  }

  /** The next `thread-stream-state-changed` change for this thread, or an IpcError after `timeoutMs`. */
  nextChange(conversationId: string, timeoutMs: number): Promise<Packet> {
    if (!this.socket || this.socket.destroyed) return Promise.reject(new IpcError("Codex disconnected"));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.followers.delete(conversationId);
        reject(new IpcError("Codex follower change timed out", true, true));
      }, timeoutMs);
      this.followers.set(conversationId, { resolve, reject, timer });
    });
  }

  /** `flush`: let frames already written (an unfollow) reach the app before the socket goes (at most 1 s). */
  close(flush = false): void {
    const socket = this.socket;
    if (flush && socket && !socket.destroyed) {
      socket.end();
      setTimeout(() => socket.destroy(), 1000).unref();
    } else socket?.destroy();
    this.fail();
  }
}
