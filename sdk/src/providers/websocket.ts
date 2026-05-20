import { EventEmitter } from "events";

export interface WsProviderConfig {
  url: string;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  pingIntervalMs?: number;
  pongTimeoutMs?: number;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

interface QueueItem {
  method: string;
  params: unknown[];
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
}

interface ActiveSubscription {
  event: string;
  callback: (data: unknown) => void;
}

export class WebSocketProvider extends EventEmitter {
  private url: string;
  private ws: WebSocket | null = null;
  private requestId = 0;
  private pendingRequests = new Map<number, PendingRequest>();
  private subscriptions = new Map<string, (data: unknown) => void>();
  private activeSubscriptions = new Map<string, ActiveSubscription>();
  private messageQueue: QueueItem[] = [];
  
  private reconnectInterval: number;
  private maxReconnectAttempts: number;
  private reconnectCount = 0;
  private isConnected = false;

  // Heartbeat Configs
  private pingInterval: number;
  private pongTimeout: number;
  private pingTimeoutId: any = null;
  private pongTimeoutId: any = null;

  constructor(config: WsProviderConfig) {
    super();
    this.url = config.url;
    this.reconnectInterval = config.reconnectIntervalMs ?? 3000;
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? 10;
    this.pingInterval = config.pingIntervalMs ?? 15000;
    this.pongTimeout = config.pongTimeoutMs ?? 5000;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);
      } catch (err) {
        reject(err);
        return;
      }

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectCount = 0;
        
        // Start heartbeat loop and flush any buffered messages
        this.startHeartbeat();
        this.flushQueue();
        this.resubscribe().catch((err) => {
          this.emit("error", new Error(`Resubscription failed: ${err.message}`));
        });

        this.emit("connected");
        resolve();
      };

      this.ws.onmessage = (event) => {
        // Reset pong timeout upon receiving any socket frame (confirms active liveness)
        this.resetPongTimeout();

        try {
          const data = JSON.parse(event.data as string);
          if (data.id && this.pendingRequests.has(data.id)) {
            const pending = this.pendingRequests.get(data.id)!;
            this.pendingRequests.delete(data.id);
            data.error ? pending.reject(new Error(data.error.message)) : pending.resolve(data.result);
          } else if (data.method === "eth_subscription") {
            const subId = data.params?.subscription;
            this.subscriptions.get(subId)?.(data.params.result);
          }
        } catch (err) {
          this.emit("error", new Error(`Failed to parse WebSocket message: ${err}`));
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.stopHeartbeat();
        this.emit("disconnected");
        this.attemptReconnect();
      };

      this.ws.onerror = (err) => {
        if (!this.isConnected) {
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

  private flushQueue(): void {
    const queue = [...this.messageQueue];
    this.messageQueue = [];
    
    for (const item of queue) {
      this.send(item.method, item.params)
        .then(item.resolve)
        .catch(item.reject);
    }
  }

  private async resubscribe(): Promise<void> {
    const oldSubs = Array.from(this.activeSubscriptions.entries());
    this.activeSubscriptions.clear();
    this.subscriptions.clear();

    for (const [oldSubId, sub] of oldSubs) {
      try {
        const newSubId = await this.subscribe(sub.event, sub.callback);
        this.emit("resubscribed", { oldSubId, newSubId, event: sub.event });
      } catch (err: any) {
        // Restore old metadata so we can retry on subsequent reconnection attempts
        this.activeSubscriptions.set(oldSubId, sub);
        this.subscriptions.set(oldSubId, sub.callback);
        this.emit("error", new Error(`Failed to resubscribe to ${sub.event}: ${err.message}`));
      }
    }
  }

  // Heartbeat/Ping-Pong Mechanics
  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.pingTimeoutId = setInterval(() => {
      if (!this.isConnected) return;

      // Heartbeat probe uses low-overhead eth_blockNumber call
      this.send("eth_blockNumber")
        .then(() => {
          this.resetPongTimeout();
        })
        .catch(() => {
          this.ws?.close();
        });

      this.pongTimeoutId = setTimeout(() => {
        this.ws?.close();
      }, this.pongTimeout);
    }, this.pingInterval);
  }

  private resetPongTimeout(): void {
    if (this.pongTimeoutId) {
      clearTimeout(this.pongTimeoutId);
      this.pongTimeoutId = null;
    }
  }

  private stopHeartbeat(): void {
    if (this.pingTimeoutId) {
      clearInterval(this.pingTimeoutId);
      this.pingTimeoutId = null;
    }
    this.resetPongTimeout();
  }

  async send(method: string, params: unknown[] = []): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!this.ws || !this.isConnected) {
        // Disconnected buffer routing
        this.messageQueue.push({ method, params, resolve, reject });
        return;
      }
      
      const id = ++this.requestId;
      this.pendingRequests.set(id, { resolve, reject });
      try {
        this.ws!.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
      } catch (err) {
        this.pendingRequests.delete(id);
        reject(err);
      }
    });
  }

  async subscribe(
    event: string,
    callback: (data: unknown) => void
  ): Promise<string> {
    const subId = (await this.send("eth_subscribe", [event])) as string;
    this.subscriptions.set(subId, callback);
    this.activeSubscriptions.set(subId, { event, callback });
    return subId;
  }

  async unsubscribe(subscriptionId: string): Promise<boolean> {
    this.subscriptions.delete(subscriptionId);
    this.activeSubscriptions.delete(subscriptionId);
    return (await this.send("eth_unsubscribe", [subscriptionId])) as boolean;
  }

  disconnect(): void {
    this.stopHeartbeat();
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
    this.pendingRequests.clear();
    this.activeSubscriptions.clear();
    this.subscriptions.clear();
    this.messageQueue = [];
  }
}
