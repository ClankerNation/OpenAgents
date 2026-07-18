// @fix-author
// Name: freebuff (via hanu-14)
// Date: 2026-07-18
//
// Startup configuration:
// [REDACTED]
//
// Runtime:
//   Platform: win32 | AMD64
//   Working dir: C:\Projects\OSS\OpenAgents
//   Shell: bash

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

/** Tracks a subscription that should be auto-restored after reconnect. */
interface SubscriptionRecord {
  event: string;          // the eth_subscribe event type (e.g. "logs")
  params: unknown[];      // full subscription params for resubscription
  callback: (data: unknown) => void;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, (data: unknown) => void>();
  private pendingSubscriptions = new Map<string, SubscriptionRecord>(); // for reconnect
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;

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
        // Resubscribe all previous subscriptions after reconnect
        this.resubscribeAll().catch((err) => this.emit("error", err));
        resolve();
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
        this.pendingRequests.clear();
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

  /** Re-establish all previous subscriptions after a reconnect. */
  private async resubscribeAll(): Promise<void> {
    for (const [oldSubId, record] of this.pendingSubscriptions.entries()) {
      try {
        const newSubId = await this.send("eth_subscribe", [record.event, ...record.params]) as string;
        this.subscriptions.set(newSubId, record.callback);
        this.pendingSubscriptions.delete(oldSubId);
        this.pendingSubscriptions.set(newSubId, record);
        this.emit("resubscribed", { oldSubId, newSubId });
      } catch (err) {
        this.emit("error", new Error(`Resubscription failed for ${record.event}: ${err}`));
      }
    }
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
    ...extraParams: unknown[]
  ): Promise<string> {
    const subId = (await this.send("eth_subscribe", [event, ...extraParams])) as string;
    this.subscriptions.set(subId, callback);
    this.pendingSubscriptions.set(subId, { event, params: extraParams, callback });
    return subId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    this.subscriptions.delete(subscriptionId);
    this.pendingSubscriptions.delete(subscriptionId);
    return (await this.send("eth_unsubscribe", [subscriptionId])) as boolean;
  }

  disconnect(): void {
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
  }
}
