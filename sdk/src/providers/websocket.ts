import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  webSocketFactory?: (url: string) => WebSocketLike;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

interface ActiveSubscription {
  event: string;
  params?: unknown;
  callback: (data: unknown) => void;
  remoteId?: string;
}

interface WebSocketLike {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onclose: (() => void) | null;
  onerror: ((err: unknown) => void) | null;
  send(data: string): void;
  close(): void;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocketLike | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, ActiveSubscription>();
  private remoteToLocal = new Map<string, string>();
  private subscriptionId = 0;
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;
  private isManualDisconnect = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private webSocketFactory: (url: string) => WebSocketLike;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this.webSocketFactory =
      config.webSocketFactory ??
      ((url: string) => new WebSocket(url) as unknown as WebSocketLike);
  }

  async connect(): Promise<void> {
    this.isManualDisconnect = false;
    return new Promise((resolve, reject) => {
      this.ws = this.webSocketFactory(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        this.emit("connected");
        this.restoreSubscriptions()
          .catch((error) => this.emit("error", error))
          .finally(resolve);
      };

      this.ws.onmessage = (event) => {
        let data: any;
        try {
          data = JSON.parse(event.data as string);
        } catch {
          return;
        }

        if (data.id && this.pendingRequests.has(data.id)) {
          const pending = this.pendingRequests.get(data.id)!;
          this.pendingRequests.delete(data.id);
          data.error
            ? pending.reject(new Error(data.error.message))
            : pending.resolve(data.result);
        } else if (data.method === "eth_subscription") {
          const subId = data.params?.subscription;
          const localId = this.remoteToLocal.get(subId);
          if (!localId) return;
          const subscription = this.subscriptions.get(localId);
          subscription?.callback(data.params.result);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.flushPendingRequests(new Error("WebSocket disconnected"));
        this.emit("disconnected");
        if (!this.isManualDisconnect) {
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
    if (this.isManualDisconnect || this.reconnectTimer) {
      return;
    }
    if (this.reconnectCount >= this.maxReconnectAttempts) {
      this.emit("maxReconnectsReached");
      return;
    }
    this.reconnectCount++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
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
    params?: unknown
  ): Promise<string> {
    const localId = `sub-${++this.subscriptionId}`;
    const subscription: ActiveSubscription = {
      event,
      params,
      callback,
    };
    this.subscriptions.set(localId, subscription);

    if (this.isConnected) {
      const remoteId = await this.createRemoteSubscription(subscription);
      subscription.remoteId = remoteId;
      this.remoteToLocal.set(remoteId, localId);
    }

    return localId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    const subscription = this.subscriptions.get(subscriptionId);
    this.subscriptions.delete(subscriptionId);
    if (!subscription?.remoteId) {
      return true;
    }

    this.remoteToLocal.delete(subscription.remoteId);
    if (!this.isConnected) {
      return true;
    }
    return (await this.send("eth_unsubscribe", [subscription.remoteId])) as boolean;
  }

  disconnect(): void {
    this.isManualDisconnect = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.flushPendingRequests(new Error("WebSocket disconnected"));
    this.remoteToLocal.clear();
    for (const subscription of this.subscriptions.values()) {
      delete subscription.remoteId;
    }
  }

  private flushPendingRequests(reason: Error): void {
    for (const pending of this.pendingRequests.values()) {
      pending.reject(reason);
    }
    this.pendingRequests.clear();
  }

  private async createRemoteSubscription(subscription: ActiveSubscription): Promise<string> {
    const params = subscription.params === undefined
      ? [subscription.event]
      : [subscription.event, subscription.params];
    return (await this.send("eth_subscribe", params)) as string;
  }

  private async restoreSubscriptions(): Promise<void> {
    this.remoteToLocal.clear();
    for (const [localId, subscription] of this.subscriptions.entries()) {
      const remoteId = await this.createRemoteSubscription(subscription);
      subscription.remoteId = remoteId;
      this.remoteToLocal.set(remoteId, localId);
    }
  }
}
