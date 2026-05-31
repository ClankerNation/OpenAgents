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

interface SubscriptionState {
  localId: string;
  remoteId: string | null;
  params: unknown[];
  callback: (data: unknown) => void;
  active: boolean;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, SubscriptionState>();
  private remoteToLocal = new Map<string, string>();
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;
  private shouldReconnect = true;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
  }

  async connect(): Promise<void> {
    this.shouldReconnect = true;
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.emit("connected");
        this.restoreSubscriptions().catch((err) => {
          this.emit("error", err);
        });
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data as string);
        if (data.id !== undefined && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          data.error ? pending.reject(new Error(data.error.message)) : pending.resolve(data.result);
        } else if (data.method === "eth_subscription") {
          const remoteId = data.params?.subscription as string | undefined;
          if (!remoteId) {
            return;
          }
          const localId = this.remoteToLocal.get(remoteId);
          if (!localId) {
            return;
          }
          const sub = this.subscriptions.get(localId);
          sub?.callback(data.params.result);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.emit("disconnected");
        if (this.shouldReconnect) {
          this.attemptReconnect();
        }
      };

      this.ws.onerror = (err) => {
        if (!this.isConnected) reject(new Error("WebSocket connection failed"));
        this.emit("error", err);
      };
    });
  }

  private attemptReconnect(): void {
    if (!this.shouldReconnect) {
      return;
    }
    if (this.reconnectCount >= this.maxReconnectAttempts) {
      this.emit("maxReconnectsReached");
      return;
    }
    this.reconnectCount++;
    setTimeout(() => {
      if (!this.shouldReconnect) {
        return;
      }
      this.connect().catch(() => this.attemptReconnect());
    }, this.reconnectInterval);
  }

  private async restoreSubscriptions(): Promise<void> {
    const activeSubscriptions = Array.from(this.subscriptions.values()).filter(
      (entry) => entry.active
    );
    for (const entry of activeSubscriptions) {
      const remoteId = (await this.send(
        "eth_subscribe",
        entry.params
      )) as string;
      if (entry.remoteId) {
        this.remoteToLocal.delete(entry.remoteId);
      }
      entry.remoteId = remoteId;
      this.remoteToLocal.set(remoteId, entry.localId);
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
    eventOrParams: string | unknown[],
    callback: (data: unknown) => void
  ): Promise<string> {
    const params = Array.isArray(eventOrParams)
      ? eventOrParams
      : [eventOrParams];
    const remoteId = (await this.send("eth_subscribe", params)) as string;
    const localId = `local-${this.requestId}-${this.subscriptions.size + 1}`;
    const state: SubscriptionState = {
      localId,
      remoteId,
      params,
      callback,
      active: true,
    };
    this.subscriptions.set(localId, state);
    this.remoteToLocal.set(remoteId, localId);
    return localId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    const subscription = this.subscriptions.get(subscriptionId);
    if (!subscription) {
      return false;
    }
    subscription.active = false;
    this.subscriptions.delete(subscriptionId);
    if (subscription.remoteId) {
      this.remoteToLocal.delete(subscription.remoteId);
      if (this.ws && this.isConnected) {
        return (await this.send("eth_unsubscribe", [
          subscription.remoteId,
        ])) as boolean;
      }
    }
    return true;
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.remoteToLocal.clear();
  }

  isReady(): boolean {
    return this.isConnected;
  }
}
