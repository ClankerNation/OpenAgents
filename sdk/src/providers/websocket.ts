/**
 * WebSocket JSON-RPC provider with automatic reconnect and subscription recovery.
 *
 * Contributor Trace:
 *   Agent: Metatron (Hermes AI celestial scribe)
 *   Platform: Hermes Agent / DeepSeek V4 Pro
 *   ISO Timestamp: 2026-05-16T21:45:00Z
 *   OS: linux, arch: x86_64, home: /home/power, cwd: /home/power/projects/OpenAgents, shell: bash
 */

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

interface ActiveSubscription {
  type: string;
  params: unknown[];
  callback: (data: unknown) => void;
  subId: string | null;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, (data: unknown) => void>();
  private activeSubscriptions = new Map<string, ActiveSubscription>();
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

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
        this.emit("connected");
        // Resubscribe to all active subscriptions after reconnect
        this.resubscribeAll().then(resolve).catch(reject);
      };

      this.ws.onmessage = (event) => {
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
        this.emit("disconnected");
        this.attemptReconnect();
      };

      this.ws.onerror = (err) => {
        if (!this.isConnected) reject(new Error("WebSocket connection failed"));
        this.emit("error", err);
      };
    });
  }

  private async resubscribeAll(): Promise<void> {
    const subKeys = Array.from(this.activeSubscriptions.keys());
    for (const key of subKeys) {
      const sub = this.activeSubscriptions.get(key);
      if (!sub) continue;
      try {
        const newSubId = (await this.send("eth_subscribe", [sub.type, ...sub.params])) as string;
        sub.subId = newSubId;
        this.subscriptions.set(newSubId, sub.callback);
      } catch (err) {
        this.emit("error", new Error(`Failed to resubscribe to ${sub.type}: ${err}`));
      }
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectCount >= this.maxReconnectAttempts) {
      this.emit("maxReconnectsReached");
      return;
    }
    this.reconnectCount++;
    this.reconnectTimer = setTimeout(() => {
      this.connect().catch(() => this.attemptReconnect());
    }, this.reconnectInterval);
  }

  async send(method: string, params: unknown[] = []): Promise<unknown> {
    if (!this.ws || !this.isConnected) {
      throw new Error("WebSocket not connected");
    }
    const id = ++this.requestId;
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.ws!.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
    });
  }

  async subscribe(
    event: string,
    callback: (data: unknown) => void,
    params: unknown[] = []
  ): Promise<string> {
    const subId = (await this.send("eth_subscribe", [event, ...params])) as string;
    this.subscriptions.set(subId, callback);
    // Track for resubscription on reconnect
    const key = `${event}:${subId}`;
    this.activeSubscriptions.set(key, {
      type: event,
      params,
      callback,
      subId,
    });
    return subId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    this.subscriptions.delete(subscriptionId);
    // Remove from active subscriptions
    for (const [key, sub] of this.activeSubscriptions) {
      if (sub.subId === subscriptionId) {
        this.activeSubscriptions.delete(key);
        break;
      }
    }
    return (await this.send("eth_unsubscribe", [subscriptionId])) as boolean;
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.subscriptions.clear();
    this.activeSubscriptions.clear();
  }
}
