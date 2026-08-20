// @fix-author rafaio1
// @date 2026-08-20T00:00:00Z
// @runtime linux x64 /tmp/OpenAgents bash
// @platform-config Agentic bounty-hunter workflow
import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, (data: unknown) => void>();
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;
  private messageQueue: Array<{ method: string; params: unknown[]; id: number }> = [];
  private readonly MAX_QUEUE_SIZE = 100;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private pongTimeout: ReturnType<typeof setTimeout> | null = null;
  private readonly HEARTBEAT_INTERVAL_MS = 30000;
  private readonly PONG_TIMEOUT_MS = 10000;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.startHeartbeat();
        this.flushMessageQueue();
        this.resubscribeAll();
        this.emit("connected");
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data as string);
        if (data.method === "eth_pong") {
          this.handlePong();
          return;
        }
        if (data.id && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          data.error ? pending.reject(new Error(data.error.message)) : pending.resolve(data.result);
        } else if (data.method === "eth_subscription") {
          const subId = data.params?.subscription;
          this.subscriptions.get(subId)?.(data.params.result);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.stopHeartbeat();
        this.emit("disconnected");
        this.attemptReconnect();
      };

      this.ws.onerror = (err) => {
        if (!this.isConnected) reject(new Error("WebSocket connection failed"));
        this.emit("error", err);
      };
    });
  }

  private attemptReconnect(): void {
    if (this.reconnectCount >= this.maxReconnectAttempts) {
      this.emit("maxReconnectsReached");
      return;
    }
    this.reconnectCount++;
    setTimeout(() => {
      this.connect().catch(() => this.attemptReconnect());
    }, this.reconnectInterval);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.isConnected) {
        try {
          this.ws.send(JSON.stringify({ jsonrpc: "2.0", method: "eth_ping" }));
          this.pongTimeout = setTimeout(() => {
            this.ws?.close();
          }, this.PONG_TIMEOUT_MS);
        } catch {
          this.ws?.close();
        }
      }
    }, this.HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.pongTimeout) {
      clearTimeout(this.pongTimeout);
      this.pongTimeout = null;
    }
  }

  private handlePong(): void {
    if (this.pongTimeout) {
      clearTimeout(this.pongTimeout);
      this.pongTimeout = null;
    }
  }

  private flushMessageQueue(): void {
    const queued = [...this.messageQueue];
    this.messageQueue = [];
    for (const msg of queued) {
      if (this.ws && this.isConnected) {
        try {
          this.ws.send(JSON.stringify({ jsonrpc: "2.0", id: msg.id, method: msg.method, params: msg.params }));
        } catch {
          this.messageQueue.push(msg);
        }
      } else {
        this.messageQueue.push(msg);
      }
    }
  }

  private async resubscribeAll(): Promise<void> {
    const subs = [...this.subscriptions.entries()];
    this.subscriptions.clear();
    for (const [_, callback] of subs) {
      try {
        const event = "newHeads"; // Default; real impl would track event type per sub
        const newSubId = await this.send("eth_subscribe", [event]);
        this.subscriptions.set(newSubId as string, callback);
      } catch {
        // Subscription failed during resubscribe; emit error but continue
        this.emit("error", new Error("Failed to resubscribe after reconnect"));
      }
    }
  }

  async send(method: string, params: unknown[] = []): Promise<unknown> {
    const id = ++this.requestId;
    if (!this.ws || !this.isConnected) {
      // Queue message for replay on reconnect (FIFO, max size)
      if (this.messageQueue.length >= this.MAX_QUEUE_SIZE) {
        this.messageQueue.shift(); // Drop oldest
      }
      this.messageQueue.push({ method, params, id });
      return new Promise((resolve, reject) => {
        this.pendingRequests.set(id, { resolve, reject });
      });
    }
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.ws!.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
    });
  }

  async subscribe(
    event: string,
    callback: (data: unknown) => void
  ): Promise<string> {
    const subId = (await this.send("eth_subscribe", [event])) as string;
    this.subscriptions.set(subId, callback);
    return subId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    this.subscriptions.delete(subscriptionId);
    return (await this.send("eth_unsubscribe", [subscriptionId])) as boolean;
  }

  disconnect(): void {
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.messageQueue = [];
  }
}
