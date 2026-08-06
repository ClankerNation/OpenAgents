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

interface Subscription {
  event: string;
  params: unknown[];
  callback: (data: unknown) => void;
  remoteId: string;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, Subscription>();
  private subscriptionIdsByRemote = new Map<string, string>();
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;
  private manuallyDisconnected = false;
  private connectPromise: Promise<void> | null = null;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
  }

  async connect(): Promise<void> {
    if (this.isConnected) return;
    if (this.connectPromise) return this.connectPromise;

    this.manuallyDisconnected = false;
    this.connectPromise = new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url);
      this.ws = ws;
      let settled = false;

      ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.emit("connected");
        if (!settled) {
          settled = true;
          resolve();
        }
        if (this.subscriptions.size > 0) {
          void this.resubscribeAll().catch((error: unknown) => {
            this.emit("error", error);
          });
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);
          if (data.id !== undefined && this.pendingRequests.has(data.id)) {
            const pending = this.pendingRequests.get(data.id)!;
            this.pendingRequests.delete(data.id);
            data.error
              ? pending.reject(new Error(data.error.message))
              : pending.resolve(data.result);
          } else if (data.method === "eth_subscription") {
            const remoteId = data.params?.subscription;
            const localId = this.subscriptionIdsByRemote.get(remoteId);
            const subscription = localId ? this.subscriptions.get(localId) : undefined;
            subscription?.callback(data.params.result);
          }
        } catch (error: unknown) {
          this.emit("error", error);
        }
      };

      ws.onclose = () => {
        if (this.ws !== ws) return;
        this.isConnected = false;
        this.emit("disconnected");
        if (!this.manuallyDisconnected) this.attemptReconnect();
      };

      ws.onerror = (err) => {
        if (!settled) {
          settled = true;
          reject(new Error("WebSocket connection failed"));
        }
        this.emit("error", err);
      };
    });

    try {
      await this.connectPromise;
    } finally {
      this.connectPromise = null;
    }
  }

  private attemptReconnect(): void {
    if (this.manuallyDisconnected || this.reconnectCount >= this.maxReconnectAttempts) {
      this.emit("maxReconnectsReached");
      return;
    }
    this.reconnectCount++;
    setTimeout(() => {
      if (!this.manuallyDisconnected) {
        this.connect().catch(() => this.attemptReconnect());
      }
    }, this.reconnectInterval);
  }

  private async resubscribeAll(): Promise<void> {
    for (const [localId, subscription] of this.subscriptions) {
      const newRemoteId = String(
        await this.send("eth_subscribe", [subscription.event, ...subscription.params]),
      );
      this.subscriptionIdsByRemote.delete(subscription.remoteId);
      subscription.remoteId = newRemoteId;
      this.subscriptionIdsByRemote.set(newRemoteId, localId);
    }
  }

  isReady(): boolean {
    return this.isConnected;
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
    if (!this.isConnected) await this.connect();
    const subId = (await this.send("eth_subscribe", [event, ...params])) as string;
    const localId = String(subId);
    this.subscriptions.set(localId, {
      event,
      params,
      callback,
      remoteId: localId,
    });
    this.subscriptionIdsByRemote.set(localId, localId);
    return localId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    const subscription = this.subscriptions.get(subscriptionId);
    if (!subscription) return false;

    this.subscriptions.delete(subscriptionId);
    this.subscriptionIdsByRemote.delete(subscription.remoteId);
    if (!this.isConnected) return true;
    return (await this.send("eth_unsubscribe", [subscription.remoteId])) as boolean;
  }

  disconnect(): void {
    this.manuallyDisconnected = true;
    const ws = this.ws;
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.subscriptions.clear();
    this.subscriptionIdsByRemote.clear();
    ws?.close();
  }
}
