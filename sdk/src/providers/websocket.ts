/**
 * @contributor doubao-agent (spiritwanghs fork)
 * @platform-config Autonomous coding agent executing GitHub bounties; user asked to do all available bounty issues.
 * @env os=linux arch=x64 home_dir=/home/user working_dir=/home/user/Doubao/chats/38444718400345090/OpenAgents shell=bash
 * @timestamp 2026-09-29T03:10:00Z
 */
import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  /** Max buffered outbound messages while disconnected. */
  maxQueueSize?: number;
  /** Heartbeat interval in ms (0 disables). */
  heartbeatIntervalMs?: number;
  /** Max silent ms before the connection is considered dead. */
  heartbeatTimeoutMs?: number;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

interface QueuedMessage {
  method: string;
  params: unknown[];
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
  private maxQueueSize: number;
  private heartbeatIntervalMs: number;
  private heartbeatTimeoutMs: number;
  private reconnectCount = 0;
  private isConnected = false;
  private queue: QueuedMessage[] = [];
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private lastActivity = 0;
  private heartbeatCheck: ReturnType<typeof setInterval> | null = null;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this.maxQueueSize = config.maxQueueSize ?? 100;
    this.heartbeatIntervalMs = config.heartbeatIntervalMs ?? 15_000;
    this.heartbeatTimeoutMs = config.heartbeatTimeoutMs ?? 45_000;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);
      let settled = false;

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.lastActivity = Date.now();
        this.startHeartbeat();
        // Flush queued messages FIFO after reconnect.
        this.flushQueue();
        // Re-subscribe to all previously active subscriptions.
        this.resubscribe();
        this.emit("connected");
        if (!settled) { settled = true; resolve(); }
      };

      this.ws.onmessage = (event) => {
        this.lastActivity = Date.now();
        const data = JSON.parse(event.data as string);
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
        if (!this.isConnected && !settled) {
          settled = true;
          reject(new Error("WebSocket connection failed"));
        }
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
    if (this.heartbeatIntervalMs <= 0) return;
    // Send a ping every interval; treat silence beyond timeout as dead.
    this.heartbeatTimer = setInterval(() => {
      if (!this.isConnected) return;
      try {
        this.ws?.send(JSON.stringify({ jsonrpc: "2.0", method: "eth_subscribe", params: ["newHeads"], id: -1 }));
        // No-op ping — some servers respond, others don't; the timeout
        // check below is what detects a dead connection.
      } catch { /* ignore */ }
    }, this.heartbeatIntervalMs);
    this.heartbeatCheck = setInterval(() => {
      if (this.isConnected && Date.now() - this.lastActivity > this.heartbeatTimeoutMs) {
        this.emit("heartbeatTimeout");
        this.ws?.close();
      }
    }, this.heartbeatIntervalMs);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) { clearInterval(this.heartbeatTimer); this.heartbeatTimer = null; }
    if (this.heartbeatCheck) { clearInterval(this.heartbeatCheck); this.heartbeatCheck = null; }
  }

  private flushQueue(): void {
    const drained = this.queue.splice(0, this.queue.length);
    for (const msg of drained) {
      this.dispatch(msg.method, msg.params).then(msg.resolve).catch(msg.reject);
    }
  }

  private resubscribe(): void {
    const active = [...this.subscriptions.keys()];
    if (active.length === 0) return;
    for (const subId of active) {
      const cb = this.subscriptions.get(subId)!;
      const eventName = this.subscriptionEvents.get(subId) ?? subId;
      this.send("eth_subscribe", [eventName])
        .then((newSubId) => {
          this.subscriptions.delete(subId);
          this.subscriptionEvents.delete(subId);
          this.subscriptions.set(newSubId as string, cb);
          this.subscriptionEvents.set(newSubId as string, eventName);
        })
        .catch(() => {});
    }
  }

  private dispatch(method: string, params: unknown[]): Promise<unknown> {
    const id = ++this.requestId;
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.ws!.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
    });
  }

  async send(method: string, params: unknown[] = []): Promise<unknown> {
    if (!this.ws || !this.isConnected) {
      // Buffer instead of dropping: FIFO queue capped at maxQueueSize.
      if (this.queue.length >= this.maxQueueSize) {
        throw new Error("WebSocket queue full");
      }
      return new Promise((resolve, reject) => {
        this.queue.push({ method, params, resolve, reject });
      });
    }
    return this.dispatch(method, params);
  }

  async subscribe(
    event: string,
    callback: (data: unknown) => void
  ): Promise<string> {
    const subId = (await this.send("eth_subscribe", [event])) as string;
    // Store the event name for resubscription, not a fabricated key.
    this.subscriptions.set(subId, callback);
    this.subscriptionEvents.set(subId, event);
    return subId;
  }

  private subscriptionEvents = new Map<string, string>();

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    this.subscriptions.delete(subscriptionId);
    this.subscriptionEvents.delete(subscriptionId);
    return (await this.send("eth_unsubscribe", [subscriptionId])) as boolean;
  }

  disconnect(): void {
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.queue = [];
  }
}
